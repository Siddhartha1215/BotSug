import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Environment setup
    USER_AGENT = "BotSugApp/1.0"
    LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "dummy")
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    # LLM Configuration
    LLM_MODEL = "llama3-70b-8192"
    LLM_PROVIDER = "groq"
    
    # Chat Configuration
    MAX_CHAT_HISTORY = 10
    MAX_RECORDS_DISPLAY = 10
    MAX_SUGGESTIONS = 3

# Set environment variables
os.environ["USER_AGENT"] = Config.USER_AGENT
os.environ["LANGCHAIN_API_KEY"] = Config.LANGCHAIN_API_KEY
os.environ["COHERE_API_KEY"] = Config.COHERE_API_KEY
os.environ["GROQ_API_KEY"] = Config.GROQ_API_KEY