import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any
import time

def extract_content(url: str) -> str:
    """
    Extract the main content from a webpage.
    
    Args:
        url: URL of the webpage to scrape
        
    Returns:
        Extracted text content from the webpage
    """
    try:
        # Send request with a user agent to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "header", "footer", "nav"]):
            script.extract()
        
        # Get text content
        text = soup.get_text(separator=' ', strip=True)
        
        # Clean up the text (remove extra whitespace)
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Limit the text to a reasonable length (8000 characters)
        return text[:8000]
    except Exception as e:
        print(f"Error extracting content from {url}: {e}")
        return ""

def scrape_search_results(search_results: List[Dict[str, Any]]) -> str:
    """
    Tool 3: Visit websites from search results and scrape content.
    
    Args:
        search_results: List of search result dictionaries with 'link' keys
        
    Returns:
        Combined extracted content from the websites
    """
    all_content = []
    
    for result in search_results:
        url = result.get("link")
        if url:
            print(f"Scraping content from: {url}")
            content = extract_content(url)
            if content:
                # Add source information and the content
                all_content.append(f"SOURCE: {url}\n{content}\n")
            
            # Pause briefly to be polite to websites
            time.sleep(1)
    
    # Combine all the extracted content
    combined_content = "\n\n".join(all_content)
    
    # Limit the total content size
    if len(combined_content) > 50000:
        combined_content = combined_content[:50000] + "... (content truncated)"
    
    print(f"Scraped {len(all_content)} websites, total content size: {len(combined_content)} characters")
    return combined_content
