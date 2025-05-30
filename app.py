from flask import Flask, render_template, request, session, redirect, url_for
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

# Suppress warnings
warnings.filterwarnings("ignore")
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
prompt = hub.pull("rlm/rag-prompt")

# State definition
class State(TypedDict):
    question: str
    context: List[Document]
    answer: str

def retrieve(state: State):
    # Increase the k parameter to get more results, e.g., k=20 for 20 students
    retrieved_docs = vector_store.similarity_search(state["question"], k=10)
    return {"context": retrieved_docs}

def generate(state: State):
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    messages = prompt.invoke({"question": state["question"], "context": docs_content})
    response = llm.invoke(messages)
    return {"answer": response.content}

graph_builder = StateGraph(State).add_sequence([retrieve, generate])
graph_builder.add_edge(START, "retrieve")
graph = graph_builder.compile()

#home
@app.route("/")
def index():
    return render_template("index.html")

#pdf chat
@app.route("/ai-chat", methods=["GET", "POST"])
def ai_chat():
    if "user" not in session:
        return redirect(url_for("auth.login"))

    response = ""
    if request.method == "POST":
        question = request.form.get("question")
        result = graph.invoke({"question": question})
        response = result["answer"]
    return render_template("chat.html", response=response)

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
