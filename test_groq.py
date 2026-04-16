import os
from groq import Groq
from dotenv import load_dotenv

# Load .env so GROQ_API_KEY is available
load_dotenv()

# Create the Groq client — it reads GROQ_API_KEY from environment automatically
client = Groq()

# Make a simple chat completion call
response = client.chat.completions.create(
    model="llama-3.1-8b-instant",   # Free, fast LLaMA 3 8B model
    messages=[
        {
            "role": "system",
            "content": "You are a helpful career advisor."
        },
        {
            "role": "user",
            "content": "In one sentence, what is the most in-demand skill for a Data Engineer in 2024?"
        }
    ],
    max_tokens=100,
    temperature=0.7,
)

# Extract the text response
answer = response.choices[0].message.content
print("Groq LLM response:")
print(answer)
print("\nModel used:", response.model)
print("Tokens used:", response.usage.total_tokens)