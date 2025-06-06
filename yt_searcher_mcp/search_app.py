import os
import time
from intent_analyzer import analyze_intent
from search_engine import google_search
from web_scraper import scrape_search_results
from youtube_query_generator import generate_youtube_query
from search_youtube import youtube_search

# Load environment variables
from dotenv import load_dotenv
import json
load_dotenv()


def run_search_pipeline(user_query, verbose=True):
    """
    Execute the complete search pipeline:
    1. Analyze and enhance the search query
    2. Perform Google search using SERP API
    3. Scrape content from search results
    4. Generate an optimized YouTube search query
    5. Return YouTube search results
    
    Args:
        user_query: The original search query from the user
        verbose: Whether to print progress to console (default: True)
        
    Returns:
        YouTube search results and context information
    """
    if verbose:
        print(f"\n{'='*80}\nProcessing search query: {user_query}\n{'='*80}\n")
    
    # Step 1: Analyze intent and enhance the query
    if verbose:
        print("\n--- STEP 1: Intent Analysis ---")
    enhanced_query = analyze_intent(user_query)

    # Step 2: Perform Google search
    if verbose:
        print("\n--- STEP 2: Google Search ---")
    search_results = google_search(enhanced_query)

    # Step 3: Scrape web content
    if verbose:
        print("\n--- STEP 3: Web Scraping ---")
    scraped_content = scrape_search_results(search_results)

    # Step 4: Generate optimized YouTube query
    if verbose:
        print("\n--- STEP 4: YouTube Query Generation ---")
    youtube_query = generate_youtube_query(scraped_content, user_query)

    # Step 5: Search YouTube
    if verbose:
        print("\n--- STEP 5: YouTube Search ---")
    youtube_results = youtube_search(youtube_query)

    return {
        "original_query": user_query,
        "enhanced_query": enhanced_query,
        "web_context": scraped_content,
        "youtube_query": youtube_query,
        "youtube_results": youtube_results
    }

def display_results(results):
    """
    Display the search results in a formatted way.
    """
    print(f"\n{'='*80}\nSEARCH RESULTS\n{'='*80}\n")
    print(f"Original Query: {results['original_query']}")
    print(f"Enhanced Query: {results['enhanced_query']}")
    print(f"YouTube Query: {results['youtube_query']}")
    
    # Display YouTube results
    yt_results = results['youtube_results']
    print(f"\nTop {len(yt_results)} YouTube Results:\n")
    for idx, video in enumerate(yt_results, start=1):
        print(f"{idx}. {video['title']}")
        print(f"   URL: {video['url']}")
        print(f"   Description: {video['description'][:100]}...\n")
    
    # Print context (truncated)
    context_preview = results['web_context'][:500] + "..." if len(results['web_context']) > 500 else results['web_context']
    print(f"\nWeb Context Preview:\n{context_preview}")
    print(f"\nTotal context size: {len(results['web_context'])} characters")

if __name__ == "__main__":
    # Check if environment variables are set
    if not os.environ.get("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. Please set it for production use.")
    
    if not os.environ.get("SERP_API_KEY"):
        print("Warning: SERP_API_KEY not set. Please set it for production use.")
    
    if not os.environ.get("YOUTUBE_API_KEY"):
        print("Warning: YOUTUBE_API_KEY not set. Using default key, which may have usage limits.")
    
    # Get user input
    user_query = input("Enter your search query (max 20 words): ")
    
    # Run the pipeline with verbose output
    start_time = time.time()
    results = run_search_pipeline(user_query, verbose=True)
    end_time = time.time()
    
    # Display results
    display_results(results)
    print(f"\nTotal processing time: {end_time - start_time:.2f} seconds")
