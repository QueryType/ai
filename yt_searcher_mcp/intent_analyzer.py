import os
import time
from openai import OpenAI
from typing import List, Dict, Any

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Load environment variables and set up OpenAI API
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
model_id = os.environ.get("OPEMAI_MODEL_ID")

def analyze_intent(query: str) -> str:
    """
    Tool 1: Analyze the search intent with GPT-4.1 and improve the search query.
    
    Args:
        query: The original user search query (max 20 words)
        
    Returns:
        Modified search query based on intent analysis
    """
    # Prepare the system message
    system_message = """
    You are an AI assistant that helps improve search queries. Your task is to:
    1. Identify the intent behind the user's search query
    2. Modify and enhance the query to make it more effective for search engines
    3. Return only the modified query without any explanations or additional text
    4. If the query is around a specific time, use current date and time to make it more relevant
    
    Make the query specific, clear, and optimized for search engines, while preserving the original intent.
    """
    
    timestamp_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    system_message += f"\nCurrent date and time: {timestamp_now}"

    # Make API call to OpenAI
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Original search query: {query}"}
        ],
        temperature=0.7,
        max_tokens=120
    )
    
    # Extract and return the improved query
    improved_query = response.choices[0].message.content.strip()
    print(f"Original query: {query}")
    print(f"Enhanced query: {improved_query}")
    
    return improved_query
