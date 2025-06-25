from langchain_core.messages import HumanMessage, SystemMessage
from langchain.chat_models import init_chat_model
from utils.data_analyzer import analyze_retrieved_data
from config import Config
import logging

logger = logging.getLogger(__name__)

# Initialize LLM
llm = init_chat_model(Config.LLM_MODEL, model_provider=Config.LLM_PROVIDER)

def generate_smart_suggestions(question, retrieved_data, user_type, conversation_context, parent_student_id=None):
    """Generate intelligent, context-aware suggested questions - updated for new schema"""
    
    try:
        # Analyze the retrieved data to understand what information is available
        data_analysis = analyze_retrieved_data(retrieved_data)
        
        # Create contextual suggestions based on data type and user type
        suggestions_prompt = f"""
        You are an expert at generating intelligent follow-up questions for an educational data system with separate semester data.
        
        Current Question: "{question}"
        User Type: {user_type}
        Data Retrieved: {len(retrieved_data)} records
        
        IMPORTANT: Grade Hierarchy (use in suggestions):
        - O = Outstanding (Highest grade)
        - A+ = Excellent (Second highest)
        - A = Very Good
        - B+ = Good
        - B = Above Average
        - C+ = Below Average
        - C = Average
        - D+ = Poor
        - D = Poor
        - F = Fail (Lowest)
        
        Data Analysis:
        {data_analysis}
        
        Conversation Context:
        {conversation_context}
        
        Database Structure Notes:
        - Students have separate CGPA for Semester 1 (cgpa_s1) and Semester 2 (cgpa_s2)
        - Attendance and marks are stored in separate tables for S1 and S2
        - Each semester has different subjects and performance metrics
        - Grade O is the highest performance indicator
        
        Generate 3 intelligent, specific follow-up questions that:
        1. Are directly related to the current data and question
        2. Provide value and insights to the user
        3. Are natural next steps in the conversation
        4. Consider the semester-based data structure
        5. Are specific and actionable (not vague)
        6. Consider the user's role and access level
        7. Use correct grade terminology (O=Outstanding, A+=Excellent, etc.)
        
        Guidelines:
        - For CGPA data: suggest comparing S1 vs S2 performance, semester progression, identifying improvement/decline
        - For attendance data: suggest comparing semesters, identifying patterns, subject-wise analysis
        - For grades data: suggest semester comparison, subject performance analysis, improvement tracking using proper grade hierarchy
        - For student info: suggest detailed semester-wise analysis, comparative studies across semesters
        - For parent users: focus on their child's semester progression and improvement areas
        - For faculty: focus on class analytics, semester comparisons, identifying students with O grades vs those needing help
        
        Format exactly as:
        1. [Specific actionable question]
        2. [Specific actionable question]  
        3. [Specific actionable question]
        
        Generate smart suggestions now:
        """
        
        messages = [
            SystemMessage(content="You are an expert at generating intelligent, contextual follow-up questions for educational data analysis with semester-based structure and proper grade hierarchy understanding. Focus on actionable insights using O=Outstanding, A+=Excellent grade system."),
            HumanMessage(content=suggestions_prompt)
        ]
        
        response = llm.invoke(messages)
        suggested_questions = response.content.strip()
        
        # Add user-type specific suggestions if LLM suggestions are too generic
        enhanced_suggestions = enhance_suggestions_by_context_updated(suggested_questions, question, data_analysis, user_type, parent_student_id)
        
        return enhanced_suggestions
        
    except Exception as e:
        logger.error(f"Error generating smart suggestions: {e}")
        # Fallback to basic suggestions
        return generate_fallback_suggestions_updated(question, user_type, parent_student_id)

def enhance_suggestions_by_context_updated(suggestions, question, data_analysis, user_type, parent_student_id):
    """Enhance suggestions based on specific context - updated for new schema"""
    
    question_lower = question.lower()
    
    # Check if suggestions are too generic and need enhancement
    if any(generic in suggestions.lower() for generic in ['try a different', 'more specific', 'check', 'ask about']):
        
        # Generate context-specific suggestions for new schema with proper grade hierarchy
        if 's1 cgpa' in data_analysis.lower() or 's2 cgpa' in data_analysis.lower():
            if user_type == "parent":
                return """1. Compare my child's CGPA improvement from Semester 1 to Semester 2
2. Which semester subjects are affecting my child's overall performance?
3. Show me my child's detailed subject-wise performance and grade breakdown (O=Outstanding, A+=Excellent)"""
            else:
                return """1. Show me students with declining CGPA from S1 to S2 who need attention
2. Compare average class performance between Semester 1 and Semester 2
3. Identify students with O grades (Outstanding) and those needing improvement"""
        
        elif 'attendance' in data_analysis.lower():
            if user_type == "parent":
                return """1. Compare my child's attendance between Semester 1 and Semester 2
2. Which semester subjects does my child have the lowest attendance in?
3. Show me my child's attendance trends and how they correlate with grades"""
            else:
                return """1. Which students have consistently low attendance across both semesters?
2. Compare attendance patterns between S1 and S2 subjects
3. Identify correlation between attendance and grade performance (O, A+, etc.)"""
        
        elif 'grade' in data_analysis.lower():
            return """1. Show me grade distribution comparison between Semester 1 and 2 (O=Outstanding to F=Fail)
2. Which subjects have the most students achieving O (Outstanding) grades?
3. Identify students with significant grade improvements from S1 to S2"""
        
        elif 'name' in question_lower and ('cgpa' in question_lower or 's1' in question_lower or 's2' in question_lower):
            return """1. Sort these students by their CGPA improvement from S1 to S2
2. Show me detailed semester-wise performance for students with O grades (Outstanding)
3. Which of these students show declining performance and need intervention?"""
    
    return suggestions

def generate_fallback_suggestions_updated(question, user_type, parent_student_id):
    """Generate fallback suggestions when smart generation fails - updated for new schema"""
    
    question_lower = question.lower()
    
    if user_type == "parent" and parent_student_id:
        return f"""1. Show me detailed semester-wise performance analysis for student {parent_student_id}
2. How does my child's performance compare with class averages (using O=Outstanding scale)?
3. What subjects need immediate attention across both semesters for my child?"""
    
    elif 'cgpa' in question_lower or 's1' in question_lower or 's2' in question_lower:
        return """1. Show me students with declining CGPA from S1 to S2 who need help
2. Compare CGPA performance across semesters and identify O grade achievers
3. Identify top 10 improving students and their success factors"""
    
    elif 'attendance' in question_lower:
        return """1. Which students have critical attendance issues across both semesters?
2. Show me semester-wise attendance patterns and their impact on grades
3. Generate attendance improvement recommendations for achieving better grades"""
    
    elif 'grade' in question_lower:
        return """1. Analyze grade distribution comparison between S1 and S2 (O=Outstanding scale)
2. Identify subjects with high O grade achievers vs those with high failure rates
3. Show me students who improved significantly from S1 to S2"""
    
    else:
        return """1. Show me overall semester-wise class performance statistics with grade breakdown
2. Identify students who need academic support across both semesters
3. Compare performance trends between Semester 1 and Semester 2 using proper grade scale"""