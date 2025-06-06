# LLM-Powered Search Pipeline with MCP Server

This application provides a search pipeline powered by LLM (GPT-4.1) that processes user queries through multiple tools and returns relevant YouTube videos.

## Features

- **Intent Analysis**: Uses GPT-4.1 to analyze search intent and enhance the query
- **Google Search**: Uses SERP API to perform Google searches
- **Web Scraping**: Extracts content from search results to build context
- **YouTube Query Generation**: Creates an optimized YouTube search query based on the collected context
- **YouTube Search**: Retrieves relevant videos using the YouTube Data API
- **MCP Server**: Exposes all these tools through a Model Context Protocol server

## Setup

### Prerequisites

- Python 3.8 or later
- Required API keys:
  - OpenAI API key
  - SERP API key
  - YouTube Data API key

### Installation

1. Clone this repository
2. Install the required packages:

```bash
pip install -r requirements.txt
```

3. Set up environment variables:

```bash
export OPENAI_API_KEY="your-openai-api-key"
export SERPAPI_API_KEY="your-serpapi-api-key"
export YOUTUBE_API_KEY="your-youtube-api-key"
```

## Usage

### Standalone Application

Run the standalone search application:

```bash
python search_app.py
```

When prompted, enter your search query (maximum 20 words).

### MCP Server

Start the MCP server:

```bash
python mcp_server.py
```

By default, the server runs on `localhost:8080`. You can customize the host and port with environment variables:

```bash
export MCP_HOST="0.0.0.0"
export MCP_PORT="9000"
python mcp_server.py
```

### Client Application

Use the provided client to interact with the MCP server:

```bash
python mcp_client.py "your search query"
```

Or run it without arguments to be prompted for input:

```bash
python mcp_client.py
```

## Available MCP Tools

- `intent_analyzer`: Analyzes search intent and enhances the query using GPT-4.1
- `search_engine`: Performs a Google search using SERP API
- `web_scraper`: Scrapes content from web pages
- `youtube_query_generator`: Generates an optimized YouTube search query based on context
- `youtube_search`: Searches YouTube for videos
- `full_pipeline`: Executes the complete search pipeline

## API Usage

You can interact with the MCP server using HTTP POST requests:

```bash
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{"tool": "full_pipeline", "params": {"query": "your search query"}}'
```

## Customization

You can modify the individual components or add new tools to the MCP server by editing the relevant Python files.

## License

This project is available under the MIT License.
