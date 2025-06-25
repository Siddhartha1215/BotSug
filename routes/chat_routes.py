from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from workflows.multi_agent_workflow import create_multi_agent_workflow
from config import Config
import datetime
import logging
import re

logger = logging.getLogger(__name__)

# Create blueprint
chat_bp = Blueprint('chat', __name__)

# Create the multi-agent workflow
multi_agent_graph = create_multi_agent_workflow()

@chat_bp.route("/ai-chat", methods=["GET", "POST"])
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
            previous_chat_history = session["chat_history"][:-1] if session.get("chat_history") else []
            
            workflow_state = {
                "question": question,
                "chat_history": previous_chat_history,
                "generated_prompt": "",
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
                "suggestions": formatted_suggestions[:Config.MAX_SUGGESTIONS],
                "chart_data": chart_data
            }
            
            session["chat_history"].append(bot_message)
            
            # Manage chat history length
            if len(session["chat_history"]) > Config.MAX_CHAT_HISTORY:
                session["chat_history"] = session["chat_history"][-Config.MAX_CHAT_HISTORY:]
            
            session.modified = True
            
            if is_ajax_request:
                return jsonify({
                    "success": True,
                    "message": bot_message,
                    "chat_history": session["chat_history"]
                })
            else:
                return redirect(url_for('chat.ai_chat'))
                
        except Exception as e:
            error_msg = f"Error in multi-agent workflow: {str(e)}"
            logger.error(error_msg)
            
            if is_ajax_request:
                return jsonify({"error": error_msg}), 500
            else:
                flash(error_msg)
                return redirect(url_for('chat.ai_chat'))
    
    # GET request - render template
    template_data = {
        "chat_history": session.get("chat_history", []),
        "user_type": user_type,
        "student_id": student_id,
        "student_name": student_name
    }
    
    return render_template("chat.html", **template_data)

@chat_bp.route("/clear-chat", methods=["POST"])
def clear_chat():
    """Clear all chat history and context"""
    if "chat_history" in session:
        session["chat_history"] = []
    if "chat_context" in session:
        session["chat_context"] = ""
    
    # Ensure session is marked as modified for proper cleanup
    session.modified = True
    
    # Log the chat history clearing for debugging
    logger.info("=== CHAT HISTORY CLEARED ===")
    logger.info(f"Session chat_history length after clear: {len(session.get('chat_history', []))}")
    
    return redirect(url_for('chat.ai_chat'))

@chat_bp.route("/ask-suggestion", methods=["POST"])
def ask_suggestion():
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    suggestion = request.form.get("suggestion")
    if suggestion:
        return redirect(url_for("chat.ai_chat", suggested_question=suggestion))
    else:
        return redirect(url_for("chat.ai_chat"))