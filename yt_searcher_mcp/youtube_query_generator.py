import os
from openai import OpenAI
from typing import List, Dict, Any

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Load environment variables and set up OpenAI API
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
model_id = os.environ.get("OPEMAI_MODEL_ID")

def generate_youtube_query(context: str, original_query: str) -> str:
    """
    Generate an optimized YouTube search query based on the scraped content.
    
    Args:
        context: The scraped content from search results
        original_query: The original user query
        
    Returns:
        An optimized query for YouTube search
    """  
    # Prepare a summary of the context (first 1000 chars) to keep prompt size manageable
    context_summary = context[:10000] + "..." if len(context) > 10000 else context
    
    # Prepare the system message
    system_message = """
    You are an AI assistant that helps create optimal YouTube search queries.
    Based on the provided search context and original query, create a very short and specific
    YouTube search query (5-15 words maximum) that would help find the most relevant videos.
    Return ONLY the search query, without any explanations or additional text.
    """
    
    # Make API call to OpenAI
    response = client.chat.completions.create(
        model=model_id,  # Using GPT-4 Turbo as a proxy for GPT-4.1
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Original query: {original_query}\n\nContext from web search:\n{context_summary}"}
        ],
        temperature=0.7,
        max_tokens=50
    )
    
    # Extract and return the YouTube query
    youtube_query = response.choices[0].message.content.strip()
    print(f"Generated YouTube query: {youtube_query}")
    
    return youtube_query
