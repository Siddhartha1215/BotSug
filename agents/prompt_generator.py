from langchain_core.messages import HumanMessage, SystemMessage
from langchain.chat_models import init_chat_model
from config import Config
import logging

logger = logging.getLogger(__name__)

# Initialize LLM
llm = init_chat_model(Config.LLM_MODEL, model_provider=Config.LLM_PROVIDER)

def prompt_generator_agent(state):
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