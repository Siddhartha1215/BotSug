from flask import Flask, render_template, request
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

# Suppress warnings
warnings.filterwarnings("ignore")
load_dotenv()

app = Flask(__name__)

# Environment setup
os.environ["USER_AGENT"] = "BotSugApp/1.0"
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "dummy")
os.environ["COHERE_API_KEY"] = os.getenv("COHERE_API_KEY")
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

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
    retrieved_docs = vector_store.similarity_search(state["question"])
    return {"context": retrieved_docs}

def generate(state: State):
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    messages = prompt.invoke({"question": state["question"], "context": docs_content})
    response = llm.invoke(messages)
    return {"answer": response.content}

graph_builder = StateGraph(State).add_sequence([retrieve, generate])
graph_builder.add_edge(START, "retrieve")
graph = graph_builder.compile()

# Flask Routes
@app.route("/", methods=["GET", "POST"])
def index():
    response = ""
    if request.method == "POST":
        question = request.form["question"]
        result = graph.invoke({"question": question})
        response = result["answer"]
    return render_template("chat.html", response=response)

if __name__ == "__main__":
    app.run(debug=True)
