# YouTube Smart Search - Gradio Interface

This is a Gradio web interface for the YouTube Smart Search application.

## Features

- Simple text input for search queries
- Interactive display of YouTube results with video previews
- Formatted display of scraped web content with clickable links
- Responsive UI that works on desktop and mobile

## Getting Started

1. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set up your environment variables in a `.env` file:
   ```
   OPENAI_API_KEY=your_openai_key
   SERP_API_KEY=your_serpapi_key
   YOUTUBE_API_KEY=your_youtube_key
   ```

3. Run the Gradio interface:
   ```
   python gradio_interface.py
   ```

4. Open the provided local URL in your browser (typically http://127.0.0.1:7860)

## Usage

1. Enter your search query in the text input field
2. Click the "Search" button or press Enter
3. View YouTube results with video previews in the left panel
4. Browse web context with clickable links in the right panel

## Notes

- The application runs a multi-step search pipeline that may take some time to complete
- YouTube embeddings are shown directly in the interface
- All links open in a new tab for convenience
