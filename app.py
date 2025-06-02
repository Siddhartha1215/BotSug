from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
import os
import warnings
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.documents import Document
from typing_extensions import List, TypedDict
from langgraph.graph import START, StateGraph
from auth import auth_bp
import datetime
import logging
import re
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from langchain_core.messages import HumanMessage, SystemMessage

# Suppress warnings
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

app = Flask(__name__)

# Environment setup
os.environ["USER_AGENT"] = "BotSugApp/1.0"
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "dummy")
os.environ["COHERE_API_KEY"] = os.getenv("COHERE_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key")
app.register_blueprint(auth_bp)

# LLM setup
llm = init_chat_model("llama3-70b-8192", model_provider="groq")

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# Multi-Agent State Definition
class MultiAgentState(TypedDict):
    question: str
    chat_history: List[dict]  # Add this field
    generated_prompt: str
    sql_query: str
    retrieved_data: List[dict]
    formatted_context: str
    answer: str
    suggested_questions: str
    parent_student_id: str
    access_denied: bool
    user_type: str
    chart_data: dict

# ========================= AGENT 0: PROMPT GENERATOR =========================
def prompt_generator_agent(state: MultiAgentState):
    """Agent 0: Generate optimized prompt based on chat history and current question"""
    question = state["question"]
    chat_history = state.get("chat_history", [])
    user_type = state.get("user_type", "faculty")
    parent_student_id = state.get("parent_student_id", None)
    
    logger.info(f"=== PROMPT GENERATOR AGENT ===")
    logger.info(f"Original Question: {question}")
    logger.info(f"Chat History Length: {len(chat_history)}")
    logger.info(f"User Type: {user_type}")
    
    # Debug: Log actual chat history content
    if chat_history:
        logger.info("Chat History Content:")
        for i, msg in enumerate(chat_history[-4:]):  # Last 4 messages
            logger.info(f"  {i+1}. {msg.get('type', 'unknown')}: {msg.get('content', '')[:100]}...")
    
    # If no chat history, return the original question
    if not chat_history or len(chat_history) < 2:
        logger.info("No significant chat history, using original question")
        return {"generated_prompt": question}
    
    # Format recent chat history for context analysis
    conversation_context = ""
    recent_messages = chat_history[-6:]  # Last 3 Q&A pairs
    
    for msg in recent_messages:
        if msg.get("type") == "user":
            conversation_context += f"User: {msg.get('content', '')}\n"
        elif msg.get("type") == "bot":
            # Only include first 150 chars of bot response for context
            bot_content = msg.get('content', '')[:150]
            conversation_context += f"Assistant: {bot_content}...\n"
    
    logger.info(f"Conversation Context:\n{conversation_context}")
    
    # Analyze conversation and generate enhanced prompt
    prompt_enhancement_request = f"""
    You are a Prompt Enhancement Agent for a student management system.
    
    Current User Question: "{question}"
    User Type: {user_type}
    
    Recent Conversation Context:
    {conversation_context}
    
    Instructions:
    - Analyze the conversation context and user question
    - If this is a follow-up question, enhance it with context from previous conversation
    - For example, if user previously asked about "student CGPA" and now asks "give me along with names", 
      enhance it to "give me student CGPA along with the names of students"
    - Generate an optimized, detailed prompt for the SQL Query Generator agent
    - Ensure the prompt retains the user's intent and important details from conversation
    - The output should be a comprehensive prompt that the SQL agent can use
    - If the current question is clear and complete, you can return it as-is
    
    Current Question: "{question}"
    
    Generate the enhanced prompt now (return only the enhanced prompt, no explanations):
    """
    
    try:
        messages = [
            SystemMessage(content="You are an expert prompt enhancement agent. Generate detailed, optimized prompts for SQL query generation based on user questions and conversation context. Return only the enhanced prompt."),
            HumanMessage(content=prompt_enhancement_request)
        ]
        
        response = llm.invoke(messages)
        generated_prompt = response.content.strip()
        
        logger.info(f"Generated Prompt: {generated_prompt}")
        
        return {"generated_prompt": generated_prompt}
        
    except Exception as e:
        logger.error(f"Error in Prompt Generator Agent: {e}")
        return {"generated_prompt": question}  # Fallback to original question

# ========================= AGENT 1: SQL QUERY GENERATOR =========================
def sql_generator_agent(state: MultiAgentState):
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
        
        # Detect if asking about specific students by checking for:
        # - Roll numbers that are not their child's
        # - Specific student names
        # - Individual student queries
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
    
    # Database schema context
    schema_context = """
    Database Schema:
    
    Table: students
    - roll_no (TEXT PRIMARY KEY) - Student roll number like '2020CS1234'
    - name (TEXT) - Student full name
    - batch (TEXT) - Academic program/batch
    - branch (TEXT) - Branch like 'Computer Science'
    - cgpa (FLOAT) - Current CGPA
    
    Table: attendance_and_marks
    - id (SERIAL PRIMARY KEY)
    - roll_no (TEXT) - References students(roll_no)
    - subject (TEXT) - Subject name
    - attended (INTEGER) - Classes attended
    - held (INTEGER) - Total classes held
    - attendance_percentage (FLOAT) - Attendance percentage
    - grade (TEXT) - Grade obtained (A, B, C, etc.)
    - ratings (TEXT) - Additional ratings
    - status (TEXT) - Pass/Fail status
    """
    
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
    You are a SQL Query Generator Agent for a student management system.
    
    {schema_context}
    
    {access_control_note}
    
    Current User Question: "{question}"
    Optimized Prompt: "{generated_prompt}"
    User Type: {user_type}
    
    Instructions:
    1. Use the optimized prompt to generate the SQL query
    2. Consider the user's intent and important details from the conversation context
    3. Generate appropriate PostgreSQL query to retrieve relevant data
    4. Join tables appropriately (students s JOIN attendance_and_marks am ON s.roll_no = am.roll_no)
    5. Apply proper filters and conditions based on both current question and conversation context
    6. STRICTLY follow access control rules for parent users
    
    Important Rules:
    - Always use table aliases (s for students, am for attendance_and_marks)
    - Use ILIKE for case-insensitive text matching
    - For parent users asking about general stats: Use aggregated functions but exclude individual identifiers
    - For parent users asking about their child: Use WHERE s.roll_no = '{parent_student_id if user_type == "parent" else ""}'
    - For comprehensive queries, limit to 20 records max
    - Return only the SQL query, nothing else
    
    Generate the SQL query now:
    """
    
    try:
        messages = [
            SystemMessage(content="You are an expert SQL query generator with strict access controls. Return only the SQL query, no explanations."),
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
        fallback_query = "SELECT s.*, am.subject, am.attendance_percentage, am.grade FROM students s LEFT JOIN attendance_and_marks am ON s.roll_no = am.roll_no LIMIT 10"
        return {"sql_query": fallback_query}

# ========================= AGENT 2: DATA EXECUTOR =========================
def data_executor_agent(state: MultiAgentState):
    """Agent 2: Execute SQL query and retrieve data"""
    sql_query = state["sql_query"]
    user_type = state.get("user_type", "faculty")
    parent_student_id = state.get("parent_student_id", None)
    
    logger.info(f"=== DATA EXECUTOR AGENT ===")
    logger.info(f"Executing SQL: {sql_query}")
    
    # Check for access denied query
    if "ACCESS_DENIED" in sql_query:
        logger.warning(f"Access denied for parent user: {parent_student_id}")
        return {
            "retrieved_data": [{"error": "ACCESS_DENIED", "message": f"You can only access information about your child (ID: {parent_student_id}) or general class statistics without individual student details."}],
            "access_denied": True
        }
    
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Additional security check for parent users
            if user_type == "parent" and parent_student_id:
                # Check if query contains individual student data for other students
                sql_lower = sql_query.lower()
                
                # If query selects individual names/roll_nos but doesn't restrict to their child
                if ("s.name" in sql_lower or "s.roll_no" in sql_lower) and parent_student_id not in sql_query:
                    # Check if it's not an aggregated query
                    if not any(agg in sql_lower for agg in ["avg(", "count(", "sum(", "max(", "min(", "group by"]):
                        logger.warning(f"Blocking parent query that accesses individual student data: {sql_query}")
                        return {
                            "retrieved_data": [{"error": "ACCESS_DENIED", "message": "You cannot access individual student details. You can only view your child's information or general class statistics."}],
                            "access_denied": True
                        }
                
                # Ensure parent-specific queries are properly restricted
                if parent_student_id not in sql_query and not any(agg in sql_lower for agg in ["avg(", "count(", "sum(", "max(", "min("]):
                    logger.info(f"Adding parent restriction to query")
                    if "WHERE" in sql_query.upper():
                        sql_query = sql_query + f" AND s.roll_no = '{parent_student_id}'"
                    else:
                        sql_query = sql_query + f" WHERE s.roll_no = '{parent_student_id}'"
                    logger.info(f"Modified SQL for parent access: {sql_query}")
            
            cur.execute(sql_query)
            results = cur.fetchall()
            
            # Convert to list of dictionaries
            retrieved_data = [dict(row) for row in results]
            
            # Print fetched records for debugging
            logger.info(f"=== FETCHED RECORDS FROM NEON DB ===")
            logger.info(f"Total records retrieved: {len(retrieved_data)}")
            
            if retrieved_data:
                logger.info("Sample records (first 3):")
                for i, record in enumerate(retrieved_data[:3], 1):
                    logger.info(f"Record {i}: {dict(record)}")
                
                # Print column names
                column_names = list(retrieved_data[0].keys()) if retrieved_data else []
                logger.info(f"Column names: {column_names}")
            else:
                logger.info("No records found in database")
            
            return {"retrieved_data": retrieved_data}
            
    except Exception as e:
        logger.error(f"Error in Data Executor Agent: {e}")
        # Return empty data on error
        return {"retrieved_data": [], "access_denied": False}
    finally:
        if 'conn' in locals():
            conn.close()

# ========================= HELPER FUNCTIONS =========================
def detect_chart_request(question):
    """Detect if the user is requesting a chart and what type"""
    chart_keywords = {
        'bar': ['bar chart', 'bar graph', 'column chart', 'bar plot'],
        'pie': ['pie chart', 'pie graph', 'pie diagram'],
        'line': ['line chart', 'line graph', 'trend chart', 'line plot'],
        'doughnut': ['doughnut chart', 'donut chart', 'ring chart'],
        'general': ['chart', 'graph', 'visualize', 'plot', 'diagram']
    }
    
    question_lower = question.lower()
    
    for chart_type, keywords in chart_keywords.items():
        for keyword in keywords:
            if keyword in question_lower:
                return chart_type
    
    return None

def generate_chart_data(question, chart_type, data):
    """Generate Chart.js configuration based on data and chart type"""
    try:
        if not data:
            return None
        
        # Simple chart generation based on common data patterns
        if chart_type == 'pie':
            # Grade distribution pie chart
            grade_counts = {}
            for record in data:
                grade = record.get('grade', 'Unknown')
                if grade:
                    grade_counts[grade] = grade_counts.get(grade, 0) + 1
            
            if grade_counts:
                return {
                    "type": "pie",
                    "data": {
                        "labels": list(grade_counts.keys()),
                        "datasets": [{
                            "data": list(grade_counts.values()),
                            "backgroundColor": ['#667eea', '#764ba2', '#10b981', '#f59e0b', '#ef4444']
                        }]
                    },
                    "options": {"responsive": True, "maintainAspectRatio": False}
                }
        
        elif chart_type == 'bar':
            # Student performance bar chart
            students = []
            cgpas = []
            for record in data:
                if record.get('name') and record.get('cgpa'):
                    students.append(record['name'][:15])  # Truncate long names
                    cgpas.append(float(record['cgpa']))
            
            if students and cgpas:
                return {
                    "type": "bar",
                    "data": {
                        "labels": students[:10],  # Limit to 10 students
                        "datasets": [{
                            "label": "CGPA",
                            "data": cgpas[:10],
                            "backgroundColor": '#667eea'
                        }]
                    },
                    "options": {"responsive": True, "maintainAspectRatio": False}
                }
        
        return None
        
    except Exception as e:
        logger.error(f"Error generating chart data: {e}")
        return None

# ========================= AGENT 3: ANSWER GENERATOR =========================
def answer_generator_agent(state: MultiAgentState):
    """Agent 3: Generate answer based on retrieved data, user question, and chat history"""
    question = state["question"]
    chat_history = state.get("chat_history", [])
    retrieved_data = state["retrieved_data"]
    user_type = state.get("user_type", "faculty")
    parent_student_id = state.get("parent_student_id", None)
    access_denied = state.get("access_denied", False)
    
    logger.info(f"=== ANSWER GENERATOR AGENT ===")
    logger.info(f"Processing {len(retrieved_data)} records with chat history of {len(chat_history)} messages")
    logger.info(f"Access denied: {access_denied}")
    
    # Check for access denied
    if access_denied or (retrieved_data and len(retrieved_data) > 0 and retrieved_data[0].get("error") == "ACCESS_DENIED"):
        access_message = retrieved_data[0].get("message", "Access denied") if retrieved_data else "Access denied"
        return {
            "answer": f"🚫 **Access Restricted**\n\n{access_message}\n\n**What you can access:**\n- Your child's specific information (ID: {parent_student_id})\n- General class statistics and averages\n- Overall performance trends\n\n**Examples of allowed questions:**\n- \"What is my child's CGPA?\"\n- \"Show me the class average CGPA\"\n- \"What is the overall attendance rate?\"",
            "suggested_questions": f"1. Show me my child's (ID: {parent_student_id}) complete academic performance\n2. What is the average CGPA of the entire class?\n3. What are the overall attendance statistics for all subjects?"
        }
    
    # Check for empty data
    if not retrieved_data:
        if user_type == "parent":
            return {
                "answer": f"I couldn't find any information for student ID {parent_student_id}. Please make sure the student ID is correct or contact the administration.",
                "suggested_questions": f"1. Show me detailed performance for student {parent_student_id}\n2. What is the class average performance?\n3. Contact administration for help"
            }
        else:
            return {
                "answer": "I couldn't find any data matching your query. Please try rephrasing your question or check if the information exists in our database.",
                "suggested_questions": "1. Try a different search term\n2. Ask about specific students or subjects\n3. Check general statistics"
            }
    
    # Format the retrieved data for the LLM
    formatted_data = ""
    for i, record in enumerate(retrieved_data[:10], 1):
        formatted_data += f"Record {i}:\n"
        for key, value in record.items():
            if value is not None:
                formatted_data += f"  {key}: {value}\n"
        formatted_data += "\n"
    
    # Format recent chat history for context
    conversation_context = ""
    if chat_history:
        recent_messages = chat_history[-6:]  # Last 3 Q&A pairs
        conversation_context = "Recent Conversation:\n"
        for msg in recent_messages:
            if msg.get("type") == "user":
                conversation_context += f"User: {msg.get('content', '')}\n"
            elif msg.get("type") == "bot":
                conversation_context += f"Assistant: {msg.get('content', '')[:300]}...\n"
        conversation_context += "\n"
    
    # Detect chart requests
    chart_type = detect_chart_request(question)
    chart_data = None
    
    # Generate main answer with conversation context
    answer_prompt = f"""
    You are an intelligent educational assistant analyzing student data with conversation memory.
    
    {conversation_context}
    
    Current User Question: "{question}"
    User Type: {user_type}
    {f"Parent Student ID: {parent_student_id}" if user_type == "parent" else ""}
    
    Retrieved Data:
    {formatted_data}
    
    Instructions:
    1. Consider the conversation context when answering
    2. If the user is asking follow-up questions, reference previous discussion appropriately
    3. Maintain continuity in the conversation (e.g., "As we discussed earlier...", "Building on the previous data...")
    4. Answer the current question comprehensively using the data
    5. Provide specific details, numbers, and insights
    6. If it's a parent asking about their child, be supportive and helpful
    7. For faculty, provide detailed analytical insights
    8. Include relevant statistics, trends, or patterns you observe
    9. Be conversational and maintain the flow of discussion
    10. For parent users, focus on their child's data or general statistics only
    
    Format your response clearly and professionally while maintaining conversation continuity.
    """
    
    try:
        messages = [
            SystemMessage(content="You are an expert educational data analyst with conversation memory. Provide comprehensive, contextual answers that build on previous discussion."),
            HumanMessage(content=answer_prompt)
        ]
        
        response = llm.invoke(messages)
        answer = response.content.strip()
        
        # Generate chart data if requested
        if chart_type and chart_type != 'general':
            chart_data = generate_chart_data(question, chart_type, retrieved_data)
            if chart_data:
                answer += f"\n\n📊 I've generated a {chart_type} chart to visualize this data."
        
        # Enhanced suggested questions generator
        suggested_questions = generate_smart_suggestions(question, retrieved_data, user_type, conversation_context, parent_student_id)
        
        return {
            "answer": answer,
            "suggested_questions": suggested_questions,
            "chart_data": chart_data,
            "formatted_context": formatted_data[:2000]
        }
        
    except Exception as e:
        logger.error(f"Error in Answer Generator Agent: {e}")
        return {
            "answer": f"I retrieved {len(retrieved_data)} records but encountered an issue processing them. Please try a more specific question.",
            "suggested_questions": "1. Ask about a specific student\n2. Try a more focused query\n3. Check system status"
        }

# ========================= ENHANCED SUGGESTION GENERATOR =========================
def generate_smart_suggestions(question, retrieved_data, user_type, conversation_context, parent_student_id=None):
    """Generate intelligent, context-aware suggested questions"""
    
    try:
        # Analyze the retrieved data to understand what information is available
        data_analysis = analyze_retrieved_data(retrieved_data)
        
        # Create contextual suggestions based on data type and user type
        suggestions_prompt = f"""
        You are an expert at generating intelligent follow-up questions for an educational data system.
        
        Current Question: "{question}"
        User Type: {user_type}
        Data Retrieved: {len(retrieved_data)} records
        
        Data Analysis:
        {data_analysis}
        
        Conversation Context:
        {conversation_context}
        
        Generate 3 intelligent, specific follow-up questions that:
        1. Are directly related to the current data and question
        2. Provide value and insights to the user
        3. Are natural next steps in the conversation
        4. Are specific and actionable (not vague)
        5. Consider the user's role and access level
        
        Guidelines:
        - For CGPA data: suggest comparing with averages, finding top/bottom performers, analyzing by branch
        - For attendance data: suggest identifying low attendance, comparing subjects, analyzing trends
        - For grades data: suggest distribution analysis, subject-wise performance, improvement areas
        - For student info: suggest detailed performance analysis, comparative studies
        - For parent users: focus on their child's improvement and support needs
        - For faculty: focus on class analytics, identifying at-risk students, performance trends
        
        Format exactly as:
        1. [Specific actionable question]
        2. [Specific actionable question]  
        3. [Specific actionable question]
        
        Generate smart suggestions now:
        """
        
        messages = [
            SystemMessage(content="You are an expert at generating intelligent, contextual follow-up questions for educational data analysis. Focus on actionable insights."),
            HumanMessage(content=suggestions_prompt)
        ]
        
        response = llm.invoke(messages)
        suggested_questions = response.content.strip()
        
        # Add user-type specific suggestions if LLM suggestions are too generic
        enhanced_suggestions = enhance_suggestions_by_context(suggested_questions, question, data_analysis, user_type, parent_student_id)
        
        return enhanced_suggestions
        
    except Exception as e:
        logger.error(f"Error generating smart suggestions: {e}")
        # Fallback to basic suggestions
        return generate_fallback_suggestions(question, user_type, parent_student_id)

def analyze_retrieved_data(retrieved_data):
    """Analyze the retrieved data to understand its structure and content"""
    if not retrieved_data:
        return "No data retrieved"
    
    analysis = []
    sample_record = retrieved_data[0]
    
    # Check what type of data we have
    has_cgpa = 'cgpa' in sample_record
    has_attendance = 'attendance_percentage' in sample_record
    has_grades = 'grade' in sample_record
    has_subjects = 'subject' in sample_record
    has_names = 'name' in sample_record
    has_branches = 'branch' in sample_record
    
    if has_cgpa:
        cgpa_values = [float(r.get('cgpa', 0)) for r in retrieved_data if r.get('cgpa')]
        if cgpa_values:
            avg_cgpa = sum(cgpa_values) / len(cgpa_values)
            analysis.append(f"CGPA data: {len(cgpa_values)} students, average CGPA: {avg_cgpa:.2f}")
    
    if has_attendance:
        attendance_values = [float(r.get('attendance_percentage', 0)) for r in retrieved_data if r.get('attendance_percentage')]
        if attendance_values:
            avg_attendance = sum(attendance_values) / len(attendance_values)
            analysis.append(f"Attendance data: average {avg_attendance:.1f}%")
    
    if has_grades:
        grades = [r.get('grade') for r in retrieved_data if r.get('grade')]
        grade_counts = {}
        for grade in grades:
            grade_counts[grade] = grade_counts.get(grade, 0) + 1
        analysis.append(f"Grade distribution: {grade_counts}")
    
    if has_subjects:
        subjects = list(set([r.get('subject') for r in retrieved_data if r.get('subject')]))
        analysis.append(f"Subjects included: {len(subjects)} ({', '.join(subjects[:3])}{'...' if len(subjects) > 3 else ''})")
    
    if has_branches:
        branches = list(set([r.get('branch') for r in retrieved_data if r.get('branch')]))
        analysis.append(f"Branches: {', '.join(branches)}")
    
    analysis.append(f"Total records: {len(retrieved_data)}")
    
    return "; ".join(analysis)

def enhance_suggestions_by_context(suggestions, question, data_analysis, user_type, parent_student_id):
    """Enhance suggestions based on specific context"""
    
    question_lower = question.lower()
    
    # Check if suggestions are too generic and need enhancement
    if any(generic in suggestions.lower() for generic in ['try a different', 'more specific', 'check', 'ask about']):
        
        # Generate context-specific suggestions
        if 'cgpa' in data_analysis.lower():
            if user_type == "parent":
                return """1. How does my child's CGPA compare to the class average?
2. Which subjects are affecting my child's CGPA the most?
3. What can my child do to improve their CGPA?"""
            else:
                return """1. Show me students with CGPA below 7.0 who need attention
2. Compare CGPA distribution across different branches
3. Identify top 10 performers and their study patterns"""
        
        elif 'attendance' in data_analysis.lower():
            if user_type == "parent":
                return """1. Which subjects does my child have low attendance in?
2. How is my child's attendance compared to class requirements?
3. Show me attendance trends for my child over time"""
            else:
                return """1. Which students have attendance below 75%?
2. Which subjects have the lowest average attendance?
3. Show me attendance patterns across different branches"""
        
        elif 'grade' in data_analysis.lower():
            return """1. Show me grade distribution across all subjects
2. Which subjects have the most failing grades?
3. Compare performance between different branches"""
        
        elif 'name' in question_lower and 'cgpa' in question_lower:
            return """1. Sort these students by CGPA from highest to lowest
2. Show me detailed academic performance for top 5 students
3. Which of these students need academic intervention?"""
    
    return suggestions

def generate_fallback_suggestions(question, user_type, parent_student_id):
    """Generate fallback suggestions when smart generation fails"""
    
    question_lower = question.lower()
    
    if user_type == "parent" and parent_student_id:
        return f"""1. Show me detailed performance analysis for student {parent_student_id}
2. Compare my child's performance with class averages
3. What subjects need immediate attention for my child?"""
    
    elif 'cgpa' in question_lower:
        return """1. Show me students with CGPA below 6.5 who need help
2. Compare CGPA performance across different branches
3. Identify top 10 students and their success factors"""
    
    elif 'attendance' in question_lower:
        return """1. Which students have critical attendance issues?
2. Show me subject-wise attendance patterns
3. Generate attendance improvement recommendations"""
    
    elif 'grade' in question_lower:
        return """1. Analyze grade distribution for pattern insights
2. Identify subjects with high failure rates
3. Show me students who improved significantly"""
    
    else:
        return """1. Show me overall class performance statistics
2. Identify students who need academic support
3. Compare performance across different subjects"""
        
# ========================= MULTI-AGENT WORKFLOW SETUP =========================
def create_multi_agent_workflow():
    """Create the multi-agent workflow graph"""
    workflow = StateGraph(MultiAgentState)
    
    # Add agents as nodes
    workflow.add_node("prompt_generator", prompt_generator_agent)
    workflow.add_node("sql_generator", sql_generator_agent)
    workflow.add_node("data_executor", data_executor_agent)
    workflow.add_node("answer_generator", answer_generator_agent)
    
    # Define the workflow sequence
    workflow.add_edge(START, "prompt_generator")
    workflow.add_edge("prompt_generator", "sql_generator")
    workflow.add_edge("sql_generator", "data_executor")
    workflow.add_edge("data_executor", "answer_generator")
    
    return workflow.compile()

# Create the multi-agent workflow
multi_agent_graph = create_multi_agent_workflow()

# ========================= FLASK ROUTES =========================
@app.route("/")
def index():
    if "user" not in session:
        return redirect(url_for("auth.login"))
    return redirect(url_for("ai_chat"))

@app.template_filter('tojsonfilter')
def to_json_filter(obj):
    if obj is None:
        return 'null'
    return json.dumps(obj, separators=(',', ':'))

@app.route("/ai-chat", methods=["GET", "POST"])
def ai_chat():
    if "user" not in session:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("auth.login"))

    # Get user context
    user_type = session.get("user_type", "faculty")
    student_id = session.get("student_id", None)
    student_name = session.get("student_name", "Student")
    
    logger.info(f"=== CHAT SESSION ===")
    logger.info(f"User Type: {user_type}, Student ID: {student_id}")
    
    # Initialize chat history
    if "chat_history" not in session:
        session["chat_history"] = []

    if request.method == "POST" and "question" in request.form:
        question = request.form.get("question")
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        is_ajax_request = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.accept_mimetypes['application/json'] > request.accept_mimetypes['text/html']
        )
        
        # Add user message to history BEFORE processing
        user_message = {
            "type": "user",
            "content": question,
            "timestamp": current_time
        }
        session["chat_history"].append(user_message)
        session.modified = True
        
        # Log chat history for debugging
        logger.info(f"Chat history before workflow: {len(session['chat_history'])} messages")
        for i, msg in enumerate(session["chat_history"][-4:]):  # Show last 4 messages
            logger.info(f"  Message {i}: {msg.get('type')} - {msg.get('content', '')[:50]}...")
        
        try:
            # Prepare state for multi-agent workflow with chat history
            # Get chat history excluding the current user message to avoid circular reference
            previous_chat_history = session["chat_history"][:-1]  # Exclude current message
            
            workflow_state = {
                "question": question,
                "chat_history": previous_chat_history,  # Add missing comma here
                "generated_prompt": "",  # Initialize this field
                "user_type": user_type,
                "parent_student_id": student_id if user_type == "parent" else None,
                "sql_query": "",
                "retrieved_data": [],
                "formatted_context": "",
                "answer": "",
                "suggested_questions": "",
                "access_denied": False,
                "chart_data": None
            }
            
            logger.info(f"=== STARTING MULTI-AGENT WORKFLOW WITH CONTEXT ===")
            logger.info(f"Workflow state chat_history length: {len(workflow_state['chat_history'])}")
            
            # Execute the multi-agent workflow
            result = multi_agent_graph.invoke(workflow_state)
            
            logger.info(f"=== WORKFLOW COMPLETED ===")
            
            response = result.get("answer", "I encountered an issue processing your request.")
            suggested_questions = result.get("suggested_questions", "")
            chart_data = result.get("chart_data", None)
            
            # Format suggested questions
            formatted_suggestions = []
            if suggested_questions:
                questions = re.findall(r'\d+\.\s*(.*?)(?=\d+\.|\Z)', suggested_questions + "0. ", re.DOTALL)
                for q in questions:
                    q = q.strip()
                    if q and len(q) > 3:
                        formatted_suggestions.append(q)
            
            # Create bot response
            bot_message = {
                "type": "bot",
                "content": response,
                "timestamp": current_time,
                "suggestions": formatted_suggestions[:3],
                "chart_data": chart_data
            }
            
            session["chat_history"].append(bot_message)
            
            # Manage chat history length (keep last 10 messages)
            if len(session["chat_history"]) > 10:
                session["chat_history"] = session["chat_history"][-10:]
            
            session.modified = True
            
            if is_ajax_request:
                return jsonify({
                    "success": True,
                    "message": bot_message,
                    "chat_history": session["chat_history"]
                })
            else:
                return redirect(url_for('ai_chat'))
                
        except Exception as e:
            error_msg = f"Error in multi-agent workflow: {str(e)}"
            logger.error(error_msg)
            
            if is_ajax_request:
                return jsonify({"error": error_msg}), 500
            else:
                flash(error_msg)
                return redirect(url_for('ai_chat'))
    
    # GET request - render template
    template_data = {
        "chat_history": session.get("chat_history", []),
        "user_type": user_type,
        "student_id": student_id,
        "student_name": student_name
    }
    
    return render_template("chat.html", **template_data)

@app.route("/clear-chat", methods=["POST"])
def clear_chat():
    if "chat_history" in session:
        session["chat_history"] = []
    if "chat_context" in session:
        session["chat_context"] = ""
    session.modified = True
    return redirect(url_for('ai_chat'))

@app.route("/ask-suggestion", methods=["POST"])
def ask_suggestion():
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    suggestion = request.form.get("suggestion")
    if suggestion:
        return redirect(url_for("ai_chat", suggested_question=suggestion))
    else:
        return redirect(url_for("ai_chat"))

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)