import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def youtube_search(query, max_results=5, api_key=None):
    """
    Search for videos on YouTube using the YouTube Data API.
    
    Args:
        query: The search query
        max_results: Maximum number of results to return (default: 5)
        api_key: YouTube Data API key (if None, will try to get from environment)
        
    Returns:
        List of dictionaries containing video information
    """
    # Get API key from environment if not provided
    api_key = os.environ.get("YOUTUBE_API_KEY")
    
    try:
        # Build the YouTube service
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # Call the search.list method to retrieve results matching the query
        request = youtube.search().list(
            q=query,
            part='snippet',
            type='video',
            maxResults=max_results
        )
        response = request.execute()

        videos = []
        for item in response.get('items', []):
            video_id = item['id']['videoId']
            title = item['snippet']['title']
            description = item['snippet']['description']
            url = f"https://www.youtube.com/watch?v={video_id}"
            videos.append({
                'title': title, 
                'description': description, 
                'url': url,
                'video_id': video_id
            })

        return videos
    except HttpError as e:
        print(f"An HTTP error occurred: {e}")
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []
