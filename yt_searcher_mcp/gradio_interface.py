import gradio as gr
import os
from search_app import run_search_pipeline
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def process_search(query):
    """
    Process the search query and format the results for Gradio display
    
    Args:
        query: The user's search query
        
    Returns:
        Formatted YouTube results HTML and scraped content
    """
    if not query.strip():
        return "Please enter a search query", "No search performed yet."
    
    # Check if environment variables are set
    missing_keys = []
    if not os.environ.get("OPENAI_API_KEY"):
        missing_keys.append("OPENAI_API_KEY")
    if not os.environ.get("SERP_API_KEY"):
        missing_keys.append("SERP_API_KEY")
    if not os.environ.get("YOUTUBE_API_KEY"):
        missing_keys.append("YOUTUBE_API_KEY (using default key with limits)")
    
    if missing_keys:
        warning = f"⚠️ Warning: The following API keys are not set: {', '.join(missing_keys)}. Some features may not work correctly."
    else:
        warning = ""
    
    # Run the search pipeline
    results = run_search_pipeline(query, verbose=False)
    
    # Format YouTube results with clickable links and video previews
    youtube_html = "<div style='margin-bottom: 20px;'>"
    if warning:
        youtube_html += f"<p style='color: #ff9800; font-weight: bold;'>{warning}</p>"
    
    youtube_html += f"<h3>Original Query: {results['original_query']}</h3>"
    youtube_html += f"<h3>Enhanced Query: {results['enhanced_query']}</h3>"
    youtube_html += f"<h3>YouTube Query: {results['youtube_query']}</h3>"
    youtube_html += "<h3>YouTube Results:</h3>"
    
    for idx, video in enumerate(results['youtube_results'], start=1):
        video_id = video['url'].split('v=')[-1]  # Extract video ID from URL
        youtube_html += f"""
        <div style='margin-bottom: 20px; border: 1px solid #ddd; padding: 15px; border-radius: 8px;'>
            <h4>{idx}. {video['title']}</h4>
            <div style='display: flex; margin-bottom: 10px;'>
                <div style='flex: 0 0 320px; margin-right: 15px;'>
                    <iframe width="320" height="180" src="https://www.youtube.com/embed/{video_id}" 
                    frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; 
                    gyroscope; picture-in-picture" allowfullscreen></iframe>
                </div>
                <div style='flex: 1;'>
                    <p>{video['description'][:250]}...</p>
                    <p><a href="{video['url']}" target="_blank">Watch on YouTube</a></p>
                </div>
            </div>
        </div>
        """
    
    youtube_html += "</div>"
    
    # Format scraped content with clickable links
    # This uses a basic regex to convert URLs in text to clickable links
    import re
    
    def linkify(text):
        url_pattern = re.compile(r'(https?://[^\s]+)')
        return url_pattern.sub(r'<a href="\1" target="_blank">\1</a>', text)
    
    scraped_content = f"<h3>Web Context:</h3><div style='white-space: pre-wrap;'>{linkify(results['web_context'])}</div>"
    
    return youtube_html, scraped_content

# Create Gradio interface
with gr.Blocks(title="YouTube Smart Search", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 🔍 YouTube Smart Search")
    gr.Markdown("""
    This application enhances your search by:
    1. Analyzing your search intent
    2. Performing a Google search with an enhanced query
    3. Scraping relevant web content
    4. Generating an optimized YouTube search query
    5. Returning the most relevant YouTube videos
    """)
    
    with gr.Row():
        search_input = gr.Textbox(
            label="Enter your search query (max 20 words)",
            placeholder="e.g., how to make sourdough bread",
            lines=1
        )
        search_button = gr.Button("Search", variant="primary")
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### YouTube Results")
            youtube_output = gr.HTML(label="YouTube Results")
        
        with gr.Column(scale=1):
            gr.Markdown("### Web Context")
            scraped_content = gr.HTML(label="Scraped Content")
    
    # Set up the button click event
    search_button.click(
        fn=process_search,
        inputs=search_input,
        outputs=[youtube_output, scraped_content]
    )
    
    # Also allow pressing Enter to submit
    search_input.submit(
        fn=process_search,
        inputs=search_input,
        outputs=[youtube_output, scraped_content]
    )

# Launch the app
if __name__ == "__main__":
    app.launch(mcp_server=True)  # share=True creates a public link
