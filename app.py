from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
import os
import warnings
from dotenv import load_dotenv
from langchain_community.vectorstores import Pinecone as LegacyPineconeStore
from pinecone import Pinecone
from langchain.chat_models import init_chat_model
from langchain import hub
from langchain_core.documents import Document
from typing_extensions import List, TypedDict
from langgraph.graph import START, StateGraph
from langchain_pinecone import PineconeVectorStore
from langchain_cohere import CohereEmbeddings
from auth import auth_bp
import datetime
from custom_prompt import RAG_PROMPT
import logging
import re


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

# Vector store and LLM setup
embeddings = CohereEmbeddings(model="embed-english-v3.0")
pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index = pc.Index("nlp")
vector_store = PineconeVectorStore(embedding=embeddings, index=index)
llm = init_chat_model("llama3-70b-8192", model_provider="groq")
prompt = RAG_PROMPT

# State definition
class State(TypedDict):
    question: str
    context: List[Document]
    answer: str
    chat_history: str
    suggested_questions: str

def retrieve(state: State):
    query = state["question"]
    logger.info(f"Query: {query}")
    
    # Detect if user is asking for "all students" or comprehensive data
    comprehensive_keywords = [
        "all students", "list all", "every student", "complete list", 
        "all details", "show all", "entire list", "full list",
        "students list", "student details", "all student records"
    ]
    is_comprehensive_query = any(keyword in query.lower() for keyword in comprehensive_keywords)
    
    if is_comprehensive_query:
        logger.info("Detected comprehensive query - using summarized retrieval")
        # For comprehensive queries, get more results but use summarized retrieval
        retrieved_docs = vector_store.similarity_search(query, k=15)
        
        # Group by student and summarize
        student_summaries = {}
        for doc in retrieved_docs:
            metadata = doc.metadata
            # Try different possible metadata keys for student identification
            student_name = (
                metadata.get('student_name') or 
                metadata.get('name') or 
                metadata.get('student') or
                'Unknown Student'
            )
            
            if student_name not in student_summaries:
                student_summaries[student_name] = {
                    'name': student_name,
                    'roll_no': metadata.get('roll_no', metadata.get('roll', 'N/A')),
                    'cgpa': metadata.get('cgpa', metadata.get('gpa', 'N/A')),
                    'content_parts': [doc.page_content[:300]]  # Store multiple content parts
                }
            else:
                # Add additional content for the same student
                student_summaries[student_name]['content_parts'].append(doc.page_content[:300])
        
        # Create summarized docs
        summarized_docs = []
        for student, info in student_summaries.items():
            # Combine content parts for better summary
            combined_content = " | ".join(info['content_parts'][:2])  # Limit to 2 content parts
            summary_content = f"Student: {info['name']} (Roll: {info['roll_no']}, CGPA: {info['cgpa']})\nDetails: {combined_content}"
            
            summarized_docs.append(Document(
                page_content=summary_content,
                metadata={
                    'student_name': info['name'], 
                    'type': 'summary',
                    'roll_no': info['roll_no'],
                    'cgpa': info['cgpa']
                }
            ))
        
        logger.info(f"Retrieved summarized data for {len(summarized_docs)} students")
        return {"context": summarized_docs[:8]}  # Limit to 8 summaries to manage context size
    else:
        # For specific queries, use normal retrieval with moderate k
        retrieved_docs = vector_store.similarity_search(query, k=6)
        logger.info(f"Retrieved {len(retrieved_docs)} documents for specific query")
        for i, doc in enumerate(retrieved_docs[:3]):  # Log first 3 docs for brevity
            logger.info(f"Doc {i+1} snippet: {doc.page_content[:100]}...")
        return {"context": retrieved_docs}

def generate(state: State):
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    logger.info(f"Total context length: {len(docs_content)} characters")
    
    # Include chat history in the context for the model
    chat_history = state.get("chat_history", "")
    
    # Calculate total context size
    total_context_length = len(docs_content) + len(chat_history) + len(state["question"])
    MAX_CONTEXT_LENGTH = 30000  # Conservative limit for Groq API
    
    # If context is too large, implement truncation strategy
    if total_context_length > MAX_CONTEXT_LENGTH:
        logger.info(f"Context too large ({total_context_length} chars), implementing truncation strategy")
        
        # Prioritize documents based on relevance (first documents are usually most relevant)
        important_docs = state["context"][:6]  # Keep top 6 most relevant documents
        docs_content = "\n\n".join(doc.page_content for doc in important_docs)
        
        # Truncate chat history more aggressively
        if len(chat_history) > 800:
            # Keep only the most recent part of chat history
            chat_history = chat_history[-800:]
            logger.info("Truncated chat history to manage context size")
        
        # Recalculate after truncation
        new_context_length = len(docs_content) + len(chat_history) + len(state["question"])
        logger.info(f"Reduced context length to {new_context_length} characters")
    
    # Update the prompt to include chat history for context
    try:
        messages = prompt.invoke({
            "question": state["question"], 
            "context": docs_content,
            "chat_history": chat_history
        })
        
        response = llm.invoke(messages)
        
        # Generate follow-up question suggestions with shorter prompt to save tokens
        follow_up_prompt = [
            {"role": "system", "content": "Based on the question and answer, suggest 3 brief follow-up questions. Format as: 1. Question 2. Question 3. Question"},
            {"role": "user", "content": f"Q: {state['question'][:200]}...\nA: {response.content[:500]}...\n\nSuggest 3 follow-ups:"}
        ]
        
        follow_ups = llm.invoke(follow_up_prompt)
        suggested_questions = follow_ups.content.strip()
        
        return {
            "answer": response.content,
            "suggested_questions": suggested_questions
        }
        
    except Exception as e:
        logger.error(f"Error in generate function: {str(e)}")
        # Fallback response if there's an issue with the main generation
        return {
            "answer": "I apologize, but I encountered an issue processing your request. The context might be too large. Please try asking about specific students or breaking down your question.",
            "suggested_questions": "1. Ask about a specific student\n2. Try a more focused question\n3. Clear chat history and start fresh"
        }

graph_builder = StateGraph(State).add_sequence([retrieve, generate])
graph_builder.add_edge(START, "retrieve")
graph = graph_builder.compile()

# home
@app.route("/")
def index():
    return render_template("index.html")

# pdf chat
@app.route("/ai-chat", methods=["GET", "POST"])
def ai_chat():
    if "user" not in session:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("auth.login"))

    # Initialize chat history if it doesn't exist
    if "chat_history" not in session:
        session["chat_history"] = []
    
    # Initialize chat context if it doesn't exist
    if "chat_context" not in session:
        session["chat_context"] = ""

    if request.method == "POST" and "question" in request.form:
        question = request.form.get("question")
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Check if it's an AJAX request
        is_ajax_request = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.accept_mimetypes['application/json'] > request.accept_mimetypes['text/html']
        )
        
        # Add user message to history
        user_message = {
            "type": "user",
            "content": question,
            "timestamp": current_time
        }
        
        session["chat_history"].append(user_message)
        session.modified = True  # Ensure session is saved
        
        # Get answer using the graph with chat context
        try:
            result = graph.invoke({
                "question": question,
                "chat_history": session["chat_context"]
            })
            
            response = result["answer"]
            suggested_questions = result.get("suggested_questions", "")
            
            # Format suggested questions for display
            formatted_suggestions = []
            if suggested_questions:
                # Parse the numbered list (assumes format like "1. Question\n2. Question\n3. Question")
                questions = re.findall(r'\d+\.\s*(.*?)(?=\d+\.|\Z)', suggested_questions + "0. ", re.DOTALL)
                for q in questions:
                    q = q.strip()
                    if q and len(q) > 3:  # Ensure question is meaningful
                        formatted_suggestions.append(q)
            
            # Add bot response to history with suggestions
            bot_message = {
                "type": "bot",
                "content": response,
                "timestamp": current_time,
                "suggestions": formatted_suggestions[:3]  # Limit to 3 suggestions
            }
            
            session["chat_history"].append(bot_message)
            
            # Dynamic chat history management based on response size
            is_large_response = len(response) > 2000
            
            if is_large_response:
                # For large responses (like "all students"), keep minimal history
                max_history_items = 2  # Only last Q&A pair
                logger.info("Large response detected - reducing chat history")
            else:
                # For normal responses, keep more history
                max_history_items = 4  # Last 2 Q&A pairs
            
            if len(session["chat_history"]) > max_history_items:
                recent_history = session["chat_history"][-max_history_items:]
            else:
                recent_history = session["chat_history"]
            
            # Format the context for the model with length limits
            context_parts = []
            for msg in recent_history:
                content = msg['content']
                # Truncate very long messages in chat history
                if len(content) > 500:
                    content = content[:500] + "..."
                context_parts.append(f"{'User' if msg['type'] == 'user' else 'Assistant'}: {content}")
            
            session["chat_context"] = "\n".join(context_parts)
            session.modified = True  # Ensure session is saved
            
            # For AJAX requests, always return JSON
            if is_ajax_request:
                return jsonify({
                    "success": True,
                    "message": bot_message,
                    "chat_history": session["chat_history"]
                })
            else:
                # For regular form submission, redirect
                return redirect(url_for('ai_chat'))
                
        except Exception as e:
            error_msg = f"Error processing your request: {str(e)}"
            logger.error(f"Error in ai_chat: {error_msg}")
            
            if is_ajax_request:
                return jsonify({"error": error_msg}), 500
            else:
                flash(error_msg)
                return redirect(url_for('ai_chat'))
    
    # For GET requests, just render the template
    return render_template("chat.html", chat_history=session.get("chat_history", []))


# Clear chat history route
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
        # Simply redirect to ai_chat with the suggestion as a parameter
        return redirect(url_for("ai_chat", suggested_question=suggestion))
    else:
        return redirect(url_for("ai_chat"))


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
