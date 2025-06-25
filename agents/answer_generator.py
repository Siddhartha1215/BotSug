from langchain_core.messages import HumanMessage, SystemMessage
from langchain.chat_models import init_chat_model
from utils.chart_generator import detect_chart_request, generate_chart_data
from utils.suggestion_generator import generate_smart_suggestions
from config import Config
import logging

logger = logging.getLogger(__name__)

# Initialize LLM
llm = init_chat_model(Config.LLM_MODEL, model_provider=Config.LLM_PROVIDER)

def answer_generator_agent(state):
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
    for i, record in enumerate(retrieved_data[:Config.MAX_RECORDS_DISPLAY], 1):
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
    
    IMPORTANT: Grade Hierarchy Understanding:
    - O = Outstanding (Highest grade, equivalent to 10 points)
    - A+ = Excellent (9 points)
    - A = Very Good (8 points)
    - B+ = Good (7 points)
    - B = Above Average (6 points)
    - C+ = Below Average (5 points)
    - C = Average (4 points)
    - D+ = Poor (3 points)
    - D = Poor (2 points)
    - F = Fail (0 points)
    
    When discussing grades:
    - Always mention that O is the highest grade (Outstanding)
    - A+ is the second highest (Excellent)
    - Use proper grade terminology in explanations
    - When comparing performance, use the correct hierarchy
    
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
    11. ALWAYS use correct grade hierarchy (O > A+ > A > B+ > B > C+ > C > D+ > D > F)
    12. Explain grade meanings when relevant (O=Outstanding, A+=Excellent, etc.)
    
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