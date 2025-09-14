# Gospel Search MCP Server

This MCP server provides semantic search capabilities for **The Gospel of Sri Ramakrishna** using ChromaDB embeddings and Google's EmbeddingGemma model.

## Features

🔍 **Advanced Semantic Search** - Find relevant passages using meaning, not just keywords  
❓ **Q&A Optimized** - Ask questions and get contextual answers from Ramakrishna's teachings  
✅ **Fact Verification** - Verify statements against the Gospel text  
📑 **Context Retrieval** - Get surrounding text for better understanding  
🔗 **Similar Passages** - Find related teachings and concepts  
📊 **Collection Stats** - Database and model information  

## Available Tools

### 1. `search_gospel(query: str, n_results: int = 3)`
General semantic search across the Gospel text.

### 2. `ask_question(question: str, n_results: int = 3)`  
Q&A optimized search for specific questions about Ramakrishna's teachings.

### 3. `verify_teaching(statement: str, n_results: int = 5)`
Fact-checking tool to verify statements against the Gospel text.

### 4. `get_context(chunk_number: int, context_size: int = 2)`
Get surrounding chunks for additional context around a specific passage.

### 5. `find_similar_passages(reference_text: str, n_results: int = 5)`
Find passages similar to a given text using clustering optimization.

### 6. `get_collection_stats()`
Get comprehensive statistics about the embeddings database.

## Setup & Usage

### 1. Install Dependencies
```bash
conda activate gemmaembeddings
pip install -r requirements.txt
```

### 2. Run the Server

#### Option A: STDIO Transport (for MCP clients like Claude Desktop, LM Studio)
```bash
# Default mode - STDIO transport
python gospel_search_server.py

# Explicitly specify STDIO
python gospel_search_server.py --transport stdio
```

#### Option B: HTTP Transport (for web clients, testing, remote access)
```bash
# HTTP server on default port 8000
python gospel_search_server.py --transport http

# HTTP server on custom host/port
python gospel_search_server.py --transport http --host 0.0.0.0 --port 3000
```

#### Option C: Using FastMCP CLI
```bash
# STDIO transport
fastmcp run gospel_search_server.py:mcp

# HTTP transport
fastmcp run gospel_search_server.py:mcp --transport http --port 8000
```

### 3. Transport Options

| Transport | Use Case | Connection |
|-----------|----------|------------|
| **STDIO** | MCP clients (Claude, LM Studio) | Process stdin/stdout |
| **HTTP** | Web clients, testing, remote access | HTTP REST API |

## Model & Data

- **Model:** Google EmbeddingGemma (300M parameters)
- **Embeddings:** 768-dimensional vectors with task optimization
- **Database:** ChromaDB with persistent storage
- **Content:** 7,862 text chunks with 100-character overlap
- **Optimization:** Prompt instructions for different search types

## Integration

### MCP Clients (STDIO)
This server works with any MCP-compatible client using STDIO transport:
- **Claude Desktop** - Add to MCP configuration
- **LM Studio** - Connect via MCP settings
- **Continue.dev** - MCP server integration
- **Custom MCP clients** - Any client supporting MCP protocol

### HTTP Clients
When running in HTTP mode, you can test with:
- **curl** - Direct HTTP API calls
- **Postman** - API testing interface
- **Web browsers** - For GET requests
- **Custom web apps** - HTTP REST integration

## Testing

### Test STDIO Mode (with LM Studio/Claude)
1. Run: `python gospel_search_server.py --transport stdio`
2. Configure in your MCP client
3. Ask questions about Ramakrishna's teachings

### Test HTTP Mode
1. Run: `python gospel_search_server.py --transport http`
2. Test with curl:
```bash
# Test server health
curl http://localhost:8000/health

# Call a tool (example)
curl -X POST http://localhost:8000/tools/search_gospel \
  -H "Content-Type: application/json" \
  -d '{"query": "What did Ramakrishna say about God?", "n_results": 3}'
```

## Example Usage

### Python Client (HTTP Mode)
```python
import requests

# Search the Gospel
response = requests.post("http://localhost:8000/tools/search_gospel", 
    json={"query": "meditation", "n_results": 3})
print(response.json())

# Ask a question
response = requests.post("http://localhost:8000/tools/ask_question",
    json={"question": "What is the nature of God according to Ramakrishna?"})
print(response.json())
```

### FastMCP Client (STDIO Mode)
```python
from fastmcp import Client
import asyncio

async def search_example():
    # This connects to the STDIO process
    client = Client("python gospel_search_server.py")
    async with client:
        # Ask a question
        result = await client.call_tool("ask_question", {
            "question": "What did Ramakrishna say about God?"
        })
        print(result)

asyncio.run(search_example())
```
