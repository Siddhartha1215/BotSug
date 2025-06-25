from langchain_core.messages import HumanMessage, SystemMessage
from langchain.chat_models import init_chat_model
from database.db_connection import DatabaseSchema
from config import Config
import logging

logger = logging.getLogger(__name__)

# Initialize LLM
llm = init_chat_model(Config.LLM_MODEL, model_provider=Config.LLM_PROVIDER)

def sql_generator_agent(state):
    """Agent 1: Generate SQL query based on user question and chat history"""
    question = state["question"]
    generated_prompt = state["generated_prompt"]
    user_type = state.get("user_type", "faculty")
    parent_student_id = state.get("parent_student_id", None)
    
    logger.info(f"=== SQL GENERATOR AGENT ===")
    logger.info(f"Generated Prompt: {generated_prompt}")
    logger.info(f"User Type: {user_type}")
    logger.info(f"Parent Student ID: {parent_student_id}")
    
    # Enhanced security check for parent users
    if user_type == "parent" and parent_student_id:
        # Check if question asks for specific student details (other than their child)
        question_lower = question.lower()
        prompt_lower = generated_prompt.lower()
        
        # Detect if asking about specific students
        security_keywords = ['roll_no', 'roll no', 'student id', 'name', 'specific student', 'individual']
        general_keywords = ['average', 'all students', 'class', 'overall', 'total', 'general', 'statistics', 'distribution']
        
        # Check if it's asking for specific info
        asking_specific = any(keyword in question_lower for keyword in security_keywords)
        asking_general = any(keyword in question_lower for keyword in general_keywords)
        
        # If asking for specific info but not general stats, restrict access
        if asking_specific and not asking_general:
            # Check if they're asking about their own child
            if parent_student_id.lower() not in question_lower and parent_student_id.lower() not in prompt_lower:
                logger.warning(f"Parent {parent_student_id} trying to access other student's specific data: {question}")
                return {
                    "sql_query": f"SELECT 'ACCESS_DENIED' as message, 'You can only access information about your child (ID: {parent_student_id}) or general class statistics' as details"
                }
    
    # Access control for parents
    access_control_note = ""
    if user_type == "parent" and parent_student_id:
        access_control_note = f"""
        IMPORTANT ACCESS CONTROL FOR PARENT USER:
        - This is a PARENT user with student ID: {parent_student_id}
        - ALLOWED: General statistics (averages, counts, distributions) without individual student names/IDs
        - ALLOWED: Information specifically about their child (WHERE s.roll_no = '{parent_student_id}')
        - DENIED: Specific information about other individual students
        - For general queries: Use aggregated data like AVG(), COUNT(), but DO NOT include individual student names or roll numbers
        - For their child's data: Use WHERE s.roll_no = '{parent_student_id}'
        """
    
    sql_prompt = f"""
    You are a SQL Query Generator Agent for a student management system with separate semester tables.
    
    {DatabaseSchema.SCHEMA_CONTEXT}
    
    {DatabaseSchema.get_grade_hierarchy_context()}
    
    When querying grades:
    - For "best/top/highest grades": Use ORDER BY with CASE statement to rank O > A+ > A > B+ > B > C+ > C > D+ > D > F
    - For "worst/lowest/failing grades": Reverse the order or filter for D+, D, F
    - For grade comparisons: Use proper grade hierarchy
    
    {access_control_note}
    
    Current User Question: "{question}"
    Optimized Prompt: "{generated_prompt}"
    User Type: {user_type}
    
    Instructions:
    1. Use the optimized prompt to generate the SQL query
    2. Consider the user's intent and important details from the conversation context
    3. Generate appropriate PostgreSQL query to retrieve relevant data
    4. For semester-specific queries, use the appropriate table (attendance_and_marks_s1 or attendance_and_marks_s2)
    5. For combined semester queries, use UNION or multiple joins as needed
    6. Join tables appropriately:
       - Students + S1: students s LEFT JOIN attendance_and_marks_s1 am_s1 ON s.roll_no = am_s1.roll_no
       - Students + S2: students s LEFT JOIN attendance_and_marks_s2 am_s2 ON s.roll_no = am_s2.roll_no
       - Students + Both: Use UNION or multiple LEFT JOINs
    7. Apply proper filters and conditions based on both current question and conversation context
    8. STRICTLY follow access control rules for parent users
    9. When sorting by grades, use proper grade hierarchy with CASE statements
    
    Query Examples:
    - Student CGPA: SELECT s.roll_no, s.name, s.cgpa_s1, s.cgpa_s2 FROM students s
    - S1 Performance: SELECT s.name, am_s1.subject, am_s1.grade FROM students s JOIN attendance_and_marks_s1 am_s1 ON s.roll_no = am_s1.roll_no
    - Top Grades: ORDER BY CASE am_s1.grade WHEN 'O' THEN 10 WHEN 'A+' THEN 9 WHEN 'A' THEN 8 WHEN 'B+' THEN 7 WHEN 'B' THEN 6 WHEN 'C+' THEN 5 WHEN 'C' THEN 4 WHEN 'D+' THEN 3 WHEN 'D' THEN 2 ELSE 0 END DESC
    - Combined Performance: Use UNION or separate queries
    
    Important Rules:
    - Always use table aliases (s, am_s1, am_s2)
    - Use ILIKE for case-insensitive text matching
    - For parent users asking about general stats: Use aggregated functions but exclude individual identifiers
    - For parent users asking about their child: Use WHERE s.roll_no = '{parent_student_id if user_type == "parent" else ""}'
    - For comprehensive queries, limit to 20 records max
    - When semester is not specified, consider both S1 and S2 data
    - Use proper grade hierarchy in ORDER BY clauses
    - Return only the SQL query, nothing else
    
    Generate the SQL query now:
    """
    
    try:
        messages = [
            SystemMessage(content="You are an expert SQL query generator with strict access controls for a multi-semester student database. Return only the SQL query, no explanations."),
            HumanMessage(content=sql_prompt)
        ]
        
        response = llm.invoke(messages)
        sql_query = response.content.strip()
        
        # Clean up the SQL query
        if sql_query.startswith("```sql"):
            sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
        elif sql_query.startswith("```"):
            sql_query = sql_query.replace("```", "").strip()
        
        logger.info(f"Generated SQL Query: {sql_query}")
        
        return {"sql_query": sql_query}
        
    except Exception as e:
        logger.error(f"Error in SQL Generator Agent: {e}")
        fallback_query = "SELECT s.roll_no, s.name, s.cgpa_s1, s.cgpa_s2 FROM students s LIMIT 10"
        return {"sql_query": fallback_query}