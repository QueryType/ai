# Gospel of Sri Ramakrishna - Semantic Search System

A complete semantic search system for **The Gospel of Sri Ramakrishna** using modern AI embeddings, ChromaDB vector database, and MCP (Model Context Protocol) integration.

## 🌟 Features

- 🔍 **Advanced Semantic Search** - Find relevant passages using meaning, not just keywords
- 🤖 **EmbeddingGemma Integration** - Google's state-of-the-art embedding model with task optimization
- 💾 **ChromaDB Vector Database** - Persistent storage with 7,862 high-quality text chunks
- 🔧 **MCP Server** - Compatible with Claude Desktop, LM Studio, and other MCP clients
- 📡 **Dual Transport** - Both STDIO and HTTP protocols supported
- ⚡ **Apple Silicon Optimized** - MPS acceleration for fast inference

## 📁 Project Structure

```
embeddings/
├── my_code/
│   ├── gospel.py              # Main embedding creation script
│   └── test_gemmaembeddings.py
├── mcp_server/
│   ├── gospel_search_server.py # FastMCP 2.0 server
│   ├── test_http.py           # HTTP mode testing
│   ├── requirements.txt       # Dependencies
│   └── README.md             # Server documentation
├── raw/
│   └── The_Gospel_of_Sri_Ramakrishna.txt
└── README.md                 # This file
```

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Create conda environment
conda create -n gemmaembeddings python=3.12
conda activate gemmaembeddings

# Install dependencies
pip install sentence-transformers chromadb torch fastmcp numpy
```

### 2. Download Models

Place the EmbeddingGemma model in:
```
models/gemmaembedding/
```

### 3. Create Embeddings

```bash
# Generate embeddings from the Gospel text
python my_code/gospel.py
```

This will:
- Clean and chunk the Gospel text (7,862 chunks with overlap)
- Generate 768-dimensional embeddings using EmbeddingGemma
- Store in ChromaDB with persistent storage

### 4. Run MCP Server

```bash
# STDIO mode (for MCP clients)
python mcp_server/gospel_search_server.py

# HTTP mode (for web clients)
python mcp_server/gospel_search_server.py --transport http --port 8000
```

## 🔧 Available Tools

The MCP server provides 6 specialized tools:

1. **`search_gospel`** - General semantic search
2. **`ask_question`** - Q&A optimized for teachings  
3. **`verify_teaching`** - Fact-checking with evidence
4. **`get_context`** - Surrounding text for context
5. **`find_similar_passages`** - Related content discovery
6. **`get_collection_stats`** - Database information

## 🤖 Integration Examples

### LM Studio
1. Configure MCP server in settings
2. Ask: *"What did Ramakrishna teach about meditation?"*
3. Get contextual answers with specific chunk references

### Claude Desktop
```json
{
  "mcpServers": {
    "gospel-search": {
      "command": "python",
      "args": ["/path/to/mcp_server/gospel_search_server.py"],
      "env": {
        "CONDA_DEFAULT_ENV": "gemmaembeddings"
      }
    }
  }
}
```

### HTTP API
```bash
curl -X POST http://localhost:8000/tools/ask_question \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the nature of God according to Ramakrishna?"}'
```

## 🎯 Technical Details

### Embedding Model
- **Model**: Google EmbeddingGemma (300M parameters)
- **Dimensions**: 768
- **Task Optimization**: Enabled with prompt instructions
- **Device**: MPS (Apple Silicon) / CPU fallback

### Text Processing
- **Source**: The Gospel of Sri Ramakrishna
- **Chunks**: 7,862 overlapping segments
- **Chunk Size**: ~500 characters
- **Overlap**: 100 characters
- **Cleaning**: Removed formatting artifacts

### Database
- **Engine**: ChromaDB
- **Storage**: Persistent local storage
- **Search**: Cosine similarity
- **Metadata**: Chunk numbers, source info, statistics

### MCP Integration
- **Framework**: FastMCP 2.0
- **Protocols**: STDIO + HTTP
- **Compatibility**: Claude Desktop, LM Studio, custom clients
- **Performance**: Optimized for real-time search

## 🛠️ Development

### Adding New Tools
```python
@mcp.tool()
def my_new_tool(param: str) -> str:
    """Tool description for LLMs."""
    # Implementation
    return result
```

### Testing
```bash
# Test HTTP mode
python mcp_server/test_http.py

# Test embeddings
python my_code/test_gemmaembeddings.py
```

### Performance Tuning
- Adjust chunk size in `gospel.py`
- Modify similarity thresholds
- Optimize batch sizes for your hardware

## 📊 Results

In 1 hour, this system enables:
- **Instant semantic search** across 7,862 spiritual teachings
- **Contextual Q&A** with specific textual evidence
- **Fact verification** against authoritative sources
- **LLM integration** for natural language interactions

## 🙏 Acknowledgments

Built with:
- **Google EmbeddingGemma** - State-of-the-art embeddings
- **ChromaDB** - Vector database excellence
- **FastMCP** - Modern MCP protocol implementation
- **The Gospel of Sri Ramakrishna** - Timeless spiritual wisdom

---

*"As many faiths, so many paths" - Now accessible through AI* 🕉️