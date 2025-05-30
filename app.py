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
import json


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
    parent_student_id: str  # Add this field
    access_denied: bool     # Add this field too

def detect_chart_request(question):
    """Detect if the user is requesting a chart and what type"""
    chart_keywords = {
        'bar': ['bar chart', 'bar graph', 'column chart', 'bar plot'],
        'pie': ['pie chart', 'pie graph', 'pie diagram'],
        'line': ['line chart', 'line graph', 'trend chart', 'line plot'],
        'doughnut': ['doughnut chart', 'donut chart', 'ring chart'],
        'general': ['chart', 'graph', 'visualize', 'plot', 'diagram', 'histogram']
    }
    
    question_lower = question.lower()
    
    for chart_type, keywords in chart_keywords.items():
        for keyword in keywords:
            if keyword in question_lower:
                return chart_type
    
    return None

def generate_chart_prompt(question, chart_type, context_data=""):
    """Generate a prompt to create Chart.js configuration"""
    return f"""
Based on the user's question: "{question}"
And this student data context: {context_data[:1000]}...

Generate a complete Chart.js configuration object for a {chart_type} chart that visualizes student performance data.

Requirements:
1. Return ONLY a valid JSON object that can be used directly with Chart.js
2. Use realistic student performance data based on the context (CGPA, grades, subjects, etc.)
3. Include proper labels, datasets, and styling
4. Use attractive colors: primary blue (#667eea), secondary purple (#764ba2), green (#10b981), orange (#f59e0b)
5. Include responsive options
6. For pie/doughnut charts, use different colors for each segment

The response should be a valid JSON object starting with {{"type": "..." }} and include all necessary Chart.js configuration.

Example structure:
{{
    "type": "{chart_type}",
    "data": {{
        "labels": [...],
        "datasets": [{{
            "label": "...",
            "data": [...],
            "backgroundColor": [...],
            "borderColor": [...],
            "borderWidth": 1
        }}]
    }},
    "options": {{
        "responsive": true,
        "maintainAspectRatio": false,
        "plugins": {{
            "legend": {{"position": "top"}},
            "tooltip": {{"enabled": true}}
        }}
    }}
}}

Generate the chart configuration now:
"""

def retrieve(state: State):
    query = state["question"]
    logger.info(f"=== RETRIEVE DEBUG ===")
    logger.info(f"Query: {query}")
    logger.info(f"State keys: {list(state.keys())}")
    logger.info(f"Full state: {state}")  # Add this to see the full state
    
    # Check if this is a parent request with student filtering
    parent_student_id = state.get("parent_student_id", None)
    is_parent_request = parent_student_id is not None
    
    logger.info(f"Parent student ID: {parent_student_id}")
    logger.info(f"Is parent request: {is_parent_request}")
    
    # If we still don't have parent_student_id but expected it, log error
    if not parent_student_id:
        logger.error("Expected parent_student_id but it's None or missing!")
    
    # Detect if user is asking for "all students" or comprehensive data
    comprehensive_keywords = [
        "all students", "list all", "every student", "complete list", 
        "all details", "show all", "entire list", "full list",
        "students list", "student details", "all student records"
    ]
    is_comprehensive_query = any(keyword in query.lower() for keyword in comprehensive_keywords)
    
    # Check if parent is asking about their specific child
    child_specific_keywords = [
        "my child", "my student", f"student id {parent_student_id}" if parent_student_id else "",
        "progress", "performance", "grades", "marks", "cgpa", "gpa"
    ]
    is_child_specific = any(keyword in query.lower() for keyword in child_specific_keywords if keyword)
    
    # For parents asking general questions (averages, statistics, etc.)
    general_query_keywords = [
        "average", "mean", "statistics", "overall", "general", "typically",
        "usually", "common", "standard", "benchmark", "comparison"
    ]
    is_general_query = any(keyword in query.lower() for keyword in general_query_keywords)
    
    logger.info(f"Is comprehensive query: {is_comprehensive_query}")
    logger.info(f"Is child specific: {is_child_specific}")
    logger.info(f"Is general query: {is_general_query}")
    
    if is_parent_request:
        logger.info("=== PARENT REQUEST DETECTED ===")
        
        if is_child_specific or f"student id {parent_student_id}" in query.lower() or parent_student_id in query:
            # Parent asking about their child - filter by student ID
            logger.info(f"Parent query about their child - filtering for student ID: {parent_student_id}")
            
            # Search with metadata filter for the specific student
            try:
                retrieved_docs = vector_store.similarity_search(
                    query, 
                    k=10,
                    filter={"roll_no": parent_student_id}  # Filter by roll_no metadata
                )
                logger.info(f"Search with roll_no filter returned {len(retrieved_docs)} docs")
            except Exception as e:
                logger.error(f"Error with roll_no filter: {e}")
                retrieved_docs = []
            
            if not retrieved_docs:
                # If no docs found with exact roll_no, try alternative metadata fields
                alternative_searches = [
                    {"student_id": parent_student_id},
                    {"roll": parent_student_id}
                ]
                
                for filter_dict in alternative_searches:
                    try:
                        retrieved_docs = vector_store.similarity_search(query, k=10, filter=filter_dict)
                        if retrieved_docs:
                            logger.info(f"Found documents using filter: {filter_dict}")
                            break
                    except Exception as e:
                        logger.error(f"Error with filter {filter_dict}: {e}")
                        continue
            
            if not retrieved_docs:
                # Return empty context - will be handled in generate function
                logger.info(f"No documents found for student ID: {parent_student_id}")
                return {"context": []}
            
            logger.info(f"Retrieved {len(retrieved_docs)} documents for student {parent_student_id}")
            return {"context": retrieved_docs}
            
        elif is_general_query:
            # Parent asking general questions - allow access to aggregate data
            logger.info("Parent asking general question - allowing access to aggregate data")
            retrieved_docs = vector_store.similarity_search(query, k=8)
            return {"context": retrieved_docs}
            
        else:
            # Parent asking about other students - deny access
            logger.info("=== ACCESS DENIED - Parent asking about other students ===")
            return {"context": [], "access_denied": True}
    
    # Faculty or non-parent users - full access
    logger.info("=== FACULTY REQUEST - Full access granted ===")
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
    # Check for access denial
    if state.get("access_denied", False):
        return {
            "answer": "I'm sorry, but as a parent, you can only access information about your child or ask general questions about averages and statistics. You don't have permission to view other students' data.",
            "suggested_questions": "1. How is my child performing?\n2. What is my child's current CGPA?\n3. What is the average CGPA of the class?"
        }
    
    # Check if no documents found for parent's child
    if len(state["context"]) == 0 and state.get("parent_student_id"):
        return {
            "answer": f"I couldn't find any information for student ID {state['parent_student_id']}. Please make sure the student ID is correct or contact the administration if you believe this is an error.",
            "suggested_questions": "1. Contact administration for help\n2. Verify the student ID\n3. Ask about general class statistics"
        }
    
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
    if "user" not in session:
        return redirect(url_for("auth.login"))
    return redirect(url_for("ai_chat"))

# Custom filter for JSON serialization in templates
@app.template_filter('tojsonfilter')
def to_json_filter(obj):
    if obj is None:
        return 'null'
    # Use separators to avoid extra spaces and ensure compact JSON
    return json.dumps(obj, separators=(',', ':'))

# pdf chat
@app.route("/ai-chat", methods=["GET", "POST"])
def ai_chat():
    if "user" not in session:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("auth.login"))

    # Check user type and set appropriate context
    user_type = session.get("user_type", "faculty")
    student_id = session.get("student_id", None)
    student_name = session.get("student_name", "Student")
    
    # Debug logging for session data
    logger.info(f"=== SESSION DEBUG ===")
    logger.info(f"User Type: {user_type}")
    logger.info(f"Student ID: {student_id}")
    logger.info(f"Student Name: {student_name}")
    logger.info(f"Session keys: {list(session.keys())}")
    
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
        
        # Detect if user wants a chart
        chart_type = detect_chart_request(question)
        chart_data = None
        
        try:
            # Prepare state for graph execution
            graph_state = {
                "question": question,
                "chat_history": session["chat_context"]
            }
            
            # IMPORTANT FIX: Add parent student ID for access control
            if user_type == "parent" and student_id:
                graph_state["parent_student_id"] = student_id
                logger.info(f"Added parent_student_id to graph state: {student_id}")
            
            # Additional debug logging
            logger.info(f"Graph state keys: {list(graph_state.keys())}")
            logger.info(f"Graph state parent_student_id: {graph_state.get('parent_student_id', 'NOT SET')}")
            
            # Get answer using the graph with chat context
            result = graph.invoke(graph_state)
            
            response = result["answer"]
            suggested_questions = result.get("suggested_questions", "")
            
            # If chart was requested, generate chart data (only for allowed content)
            if chart_type and chart_type != 'general' and not result.get("access_denied", False):
                try:
                    # Get context data for chart generation
                    docs_content = "\n\n".join(doc.page_content for doc in result.get("context", []))
                    chart_prompt = generate_chart_prompt(question, chart_type, docs_content)
                    chart_response = llm.invoke([{"role": "user", "content": chart_prompt}])
                    
                    # Extract JSON from the response
                    chart_response_content = chart_response.content.strip()
                    
                    # Try to find JSON in the response
                    json_start = chart_response_content.find('{')
                    json_end = chart_response_content.rfind('}') + 1
                    
                    if json_start != -1 and json_end > json_start:
                        chart_json = chart_response_content[json_start:json_end]
                        chart_data = json.loads(chart_json)
                        
                        # Add some default styling if missing
                        if 'options' not in chart_data:
                            chart_data['options'] = {}
                        
                        chart_data['options'].update({
                            'responsive': True,
                            'maintainAspectRatio': False,
                            'plugins': {
                                'legend': {
                                    'position': 'top',
                                },
                                'tooltip': {
                                    'enabled': True,
                                    'backgroundColor': 'rgba(0, 0, 0, 0.8)',
                                    'titleColor': '#fff',
                                    'bodyColor': '#fff'
                                }
                            }
                        })
                        
                        response += f"\n\n📊 I've generated a {chart_type} chart to visualize the data above."
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing chart JSON: {e}")
                    chart_data = None
                    response += "\n\n⚠️ I tried to create a chart but encountered a formatting issue. The data above should still be helpful!"
                except Exception as e:
                    logger.error(f"Error generating chart: {e}")
                    chart_data = None
            
            # Format suggested questions for display
            formatted_suggestions = []
            if suggested_questions:
                # Parse the numbered list (assumes format like "1. Question\n2. Question\n3. Question")
                questions = re.findall(r'\d+\.\s*(.*?)(?=\d+\.|\Z)', suggested_questions + "0. ", re.DOTALL)
                for q in questions:
                    q = q.strip()
                    if q and len(q) > 3:  # Ensure question is meaningful
                        formatted_suggestions.append(q)
            
            # Add user-type specific suggestions
            if user_type == "parent":
                if student_id:
                    parent_suggestions = [
                        f"How is my child (ID: {student_id}) performing?",
                        f"What subjects need attention for student {student_id}?",
                        "What's the average CGPA of the class?"
                    ]
                    formatted_suggestions.extend(parent_suggestions[:2])
            elif chart_data:
                chart_suggestions = [
                    f"Show me a different type of chart for this data",
                    f"Create a line chart for trend analysis",
                    f"Generate a pie chart for grade distribution"
                ]
                formatted_suggestions.extend(chart_suggestions[:2])
            
            # Add bot response to history with suggestions and chart data
            bot_message = {
                "type": "bot",
                "content": response,
                "timestamp": current_time,
                "suggestions": formatted_suggestions[:3],  # Limit to 3 suggestions
                "chart_data": chart_data
            }
            
            session["chat_history"].append(bot_message)
            
            # Dynamic chat history management based on response size
            is_large_response = len(response) > 2000 or chart_data is not None
            
            if is_large_response:
                # For large responses (like "all students"), keep minimal history
                max_history_items = 2  # Only last Q&A pair
                logger.info("Large response/chart detected - reducing chat history")
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
    
    # For GET requests, render template with user context
    template_data = {
        "chat_history": session.get("chat_history", []),
        "user_type": user_type,
        "student_id": student_id,
        "student_name": student_name
    }
    
    return render_template("chat.html", **template_data)

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
