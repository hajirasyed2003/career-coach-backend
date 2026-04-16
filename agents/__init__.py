# agents/__init__.py
from crewai import LLM
import os
from dotenv import load_dotenv

load_dotenv()

# One shared LLM instance — all three agents use this same object
# CrewAI's LLM wrapper handles the Groq API call format internally
groq_llm = LLM(
    model="groq/llama-3.1-8b-instant",   # groq/ prefix tells CrewAI which provider
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.7,                # 0 = deterministic, 1 = creative. 0.7 is balanced
    max_tokens=500,                # max tokens PER agent response
)