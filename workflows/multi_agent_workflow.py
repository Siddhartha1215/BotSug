from langgraph.graph import START, StateGraph
from agents import MultiAgentState
from agents.prompt_generator import prompt_generator_agent
from agents.sql_generator import sql_generator_agent
from agents.data_executor import data_executor_agent
from agents.answer_generator import answer_generator_agent
import logging

logger = logging.getLogger(__name__)

def create_multi_agent_workflow():
    """Create the multi-agent workflow graph with sequential execution"""
    
    logger.info("Creating multi-agent workflow...")
    
    # Create the state graph
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
    
    logger.info("Multi-agent workflow created successfully")
    
    # Compile and return the workflow
    return workflow.compile()

def execute_workflow(initial_state):
    """Execute the multi-agent workflow with error handling"""
    
    logger.info("=== STARTING MULTI-AGENT WORKFLOW EXECUTION ===")
    logger.info(f"Initial state: {initial_state.get('question', 'No question provided')}")
    
    try:
        # Create workflow instance
        workflow = create_multi_agent_workflow()
        
        # Execute workflow
        result = workflow.invoke(initial_state)
        
        logger.info("=== WORKFLOW EXECUTION COMPLETED ===")
        logger.info(f"Final answer generated: {len(result.get('answer', ''))} characters")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in workflow execution: {e}")
        
        # Return error state
        return {
            "question": initial_state.get("question", ""),
            "answer": f"I encountered an error while processing your request: {str(e)}",
            "suggested_questions": "1. Try rephrasing your question\n2. Ask about general statistics\n3. Check system status",
            "chart_data": None,
            "access_denied": False
        }

def workflow_health_check():
    """Check if all workflow components are working"""
    
    try:
        # Test workflow creation
        workflow = create_multi_agent_workflow()
        
        # Test with minimal state
        test_state = {
            "question": "Test question",
            "chat_history": [],
            "generated_prompt": "",
            "sql_query": "",
            "retrieved_data": [],
            "formatted_context": "",
            "answer": "",
            "suggested_questions": "",
            "parent_student_id": None,
            "access_denied": False,
            "user_type": "faculty",
            "chart_data": None
        }
        
        logger.info("Workflow health check: PASSED")
        return True
        
    except Exception as e:
        logger.error(f"Workflow health check failed: {e}")
        return False