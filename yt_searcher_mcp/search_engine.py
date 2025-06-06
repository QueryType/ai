import os
import json
from serpapi import GoogleSearch
from typing import List, Dict, Any

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def google_search(query: str, num_results: int = 10) -> List[Dict[str, Any]]:
    """
    Tool 2: Perform a Google search using SERP API.
    
    Args:
        query: The search query
        num_results: Number of results to return (default: 10)
        
    Returns:
        List of dictionaries containing search results with title, link, and snippet
    """
  
    # Set your SerpAPI key
    api_key = os.environ.get("SERP_API_KEY")

    # Set up the search parameters
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": num_results
    }
    
    # Perform the search
    search = GoogleSearch(params)
    results = search.get_dict()
    
    # Extract organic results
    search_results = []
    if "organic_results" in results:
        for result in results["organic_results"][:num_results]:
            search_results.append({
                "title": result.get("title", ""),
                "link": result.get("link", ""),
                "snippet": result.get("snippet", "")
            })
    
    print(f"Found {len(search_results)} search results for query: {query}")
    return search_results
