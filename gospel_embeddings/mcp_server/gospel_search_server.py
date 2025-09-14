#!/usr/bin/env python3
"""
Gospel Search MCP Server

This MCP server provides tools for semantic search and analysis of the Gospel of Sri Ramakrishna
using ChromaDB embeddings and the EmbeddingGemma model.

Built with FastMCP 2.0 for high performance and easy integration.

Supports multiple transport protocols:
- STDIO: For MCP clients (Claude Desktop, LM Studio)
- HTTP: For web clients, testing, and remote access

Usage:
    # STDIO mode (default)
    python gospel_search_server.py
    
    # HTTP mode
    python gospel_search_server.py --transport http --port 8000
    
    # HTTP mode with custom host/port
    python gospel_search_server.py --transport http --host 0.0.0.0 --port 3000
"""

import os
import sys
from typing import Dict, List, Any

# Add the parent directory to the path to import our gospel module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP

# Import our embedding components
import torch
from sentence_transformers import SentenceTransformer
import chromadb

# Global variables for the model and database
model = None
collection = None
client = None

def initialize_gospel_search():
    """Initialize the embedding model and ChromaDB connection."""
    global model, collection, client
    
    try:
        # Initialize the model
        model_path = "/Volumes/d/code/aiml/embeddings/models/gemmaembedding"
        model = SentenceTransformer(model_path)
        
        # Set device
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        
        # Initialize ChromaDB
        db_path = "/Volumes/d/code/aiml/embeddings/chromadb_storage"
        client = chromadb.PersistentClient(path=db_path)
        collection = client.get_collection("gospel_embeddings")
        
        print(f"✅ Gospel Search MCP Server initialized successfully!")
        print(f"   Model: {model_path}")
        print(f"   Database: {db_path}")
        print(f"   Collection: gospel_embeddings ({collection.count()} chunks)")
        print(f"   Device: {device}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to initialize Gospel Search: {e}")
        return False

def search_gospel_embeddings(query: str, task_type: str = "search result", n_results: int = 3) -> List[Dict]:
    """Search the gospel embeddings with task-specific optimization."""
    global model, collection
    
    # Format query with task-specific prompt
    formatted_query = f"task: {task_type} | query: {query}"
    
    # Get device
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    
    # Create query embedding
    query_embedding = model.encode([formatted_query], device=device)
    
    # Search ChromaDB
    results = collection.query(
        query_embeddings=query_embedding.tolist(),
        n_results=n_results
    )
    
    # Format results
    formatted_results = []
    for i, (doc, distance, metadata) in enumerate(zip(
        results['documents'][0], 
        results['distances'][0], 
        results['metadatas'][0]
    )):
        formatted_results.append({
            'rank': i + 1,
            'similarity_score': round(1 - distance, 4),
            'chunk_number': metadata['chunk_number'],
            'text': doc,
            'metadata': metadata,
            'distance': round(distance, 4)
        })
    
    return formatted_results

def get_context_around_chunk(chunk_number: int, context_size: int = 2) -> Dict:
    """Get surrounding chunks for additional context."""
    global collection
    
    # Get the specific chunk and surrounding ones
    try:
        # Calculate the range of chunks to retrieve
        start_chunk = max(0, chunk_number - context_size)
        end_chunk = chunk_number + context_size + 1
        
        # Get chunks in range
        chunk_ids = [f"chunk_{i}" for i in range(start_chunk, end_chunk)]
        
        # Query ChromaDB for these specific chunks
        results = collection.get(ids=chunk_ids)
        
        context_chunks = []
        for i, (chunk_id, doc, metadata) in enumerate(zip(
            results['ids'], 
            results['documents'], 
            results['metadatas']
        )):
            context_chunks.append({
                'chunk_number': metadata['chunk_number'],
                'text': doc,
                'is_target': metadata['chunk_number'] == chunk_number,
                'position_relative': metadata['chunk_number'] - chunk_number
            })
        
        # Sort by chunk number
        context_chunks.sort(key=lambda x: x['chunk_number'])
        
        return {
            'target_chunk': chunk_number,
            'context_size': context_size,
            'total_chunks': len(context_chunks),
            'context': context_chunks
        }
        
    except Exception as e:
        return {'error': f"Failed to get context: {str(e)}"}

# Initialize FastMCP server
mcp = FastMCP("Gospel Search Server")

# Initialize the gospel search on startup
if not initialize_gospel_search():
    print("❌ Failed to initialize Gospel search. Exiting.")
    sys.exit(1)

@mcp.tool()
def search_gospel(query: str, n_results: int = 3) -> str:
    """Search the Gospel of Sri Ramakrishna using semantic embeddings.
    
    Args:
        query: The search query or question
        n_results: Number of results to return (default: 3, max: 10)
    
    Returns:
        Formatted search results with similarity scores and text content
    """
    if not collection:
        return "❌ Gospel search not initialized. Please check the server setup."
    
    n_results = min(n_results, 10)  # Cap at 10 results
    
    try:
        results = search_gospel_embeddings(query, "search result", n_results)
        
        response = f"🔍 **Search Results for:** '{query}'\n\n"
        for result in results:
            response += f"**{result['rank']}. Similarity: {result['similarity_score']} | Chunk {result['chunk_number']}**\n"
            response += f"📖 {result['text']}\n"
            response += "─" * 80 + "\n\n"
        
        return response
        
    except Exception as e:
        return f"❌ Error searching: {str(e)}"

@mcp.tool()
def ask_question(question: str, n_results: int = 3) -> str:
    """Ask a specific question about Ramakrishna's teachings (optimized for Q&A).
    
    Args:
        question: The question about Ramakrishna's teachings
        n_results: Number of results to return (default: 3, max: 10)
    
    Returns:
        Formatted Q&A results with relevant teachings and context
    """
    if not collection:
        return "❌ Gospel search not initialized. Please check the server setup."
    
    n_results = min(n_results, 10)
    
    try:
        results = search_gospel_embeddings(question, "question answering", n_results)
        
        response = f"❓ **Question:** {question}\n\n**📚 Relevant Teachings:**\n\n"
        for result in results:
            response += f"**{result['rank']}. Similarity: {result['similarity_score']} | Chunk {result['chunk_number']}**\n"
            response += f"📖 {result['text']}\n"
            response += "─" * 80 + "\n\n"
        
        return response
        
    except Exception as e:
        return f"❌ Error asking question: {str(e)}"

@mcp.tool()
def verify_teaching(statement: str, n_results: int = 5) -> str:
    """Verify if a specific teaching or statement appears in the Gospel (fact-checking optimized).
    
    Args:
        statement: The teaching or statement to verify
        n_results: Number of results to return (default: 5, max: 10)
    
    Returns:
        Verification results with evidence and confidence assessment
    """
    if not collection:
        return "❌ Gospel search not initialized. Please check the server setup."
    
    n_results = min(n_results, 10)
    
    try:
        results = search_gospel_embeddings(statement, "fact checking", n_results)
        
        response = f"✅ **Verifying Statement:** {statement}\n\n**🔍 Evidence Found:**\n\n"
        for result in results:
            response += f"**{result['rank']}. Similarity: {result['similarity_score']} | Chunk {result['chunk_number']}**\n"
            response += f"📖 {result['text']}\n"
            response += "─" * 80 + "\n\n"
        
        # Add verification summary
        highest_score = results[0]['similarity_score'] if results else 0
        if highest_score > 0.15:
            response += f"**✅ Verification Result:** Strong evidence found (highest similarity: {highest_score})\n"
        elif highest_score > 0.08:
            response += f"**⚠️ Verification Result:** Some evidence found (highest similarity: {highest_score})\n"
        else:
            response += f"**❌ Verification Result:** Limited evidence found (highest similarity: {highest_score})\n"
        
        return response
        
    except Exception as e:
        return f"❌ Error verifying teaching: {str(e)}"

@mcp.tool()
def get_context(chunk_number: int, context_size: int = 2) -> str:
    """Get surrounding text chunks for additional context around a specific chunk.
    
    Args:
        chunk_number: The chunk number to get context around
        context_size: Number of chunks before and after to include (default: 2, max: 5)
    
    Returns:
        Context chunks showing the target chunk and surrounding text
    """
    if not collection:
        return "❌ Gospel search not initialized. Please check the server setup."
    
    context_size = min(context_size, 5)
    
    try:
        context_result = get_context_around_chunk(chunk_number, context_size)
        
        if 'error' in context_result:
            return f"❌ Error: {context_result['error']}"
        
        response = f"📑 **Context around Chunk {chunk_number}** (±{context_size} chunks)\n\n"
        
        for chunk in context_result['context']:
            marker = "🎯" if chunk['is_target'] else "📄"
            position = f" ({chunk['position_relative']:+d})" if not chunk['is_target'] else " (TARGET)"
            
            response += f"**{marker} Chunk {chunk['chunk_number']}{position}**\n"
            response += f"📖 {chunk['text']}\n"
            response += "─" * 80 + "\n\n"
        
        return response
        
    except Exception as e:
        return f"❌ Error getting context: {str(e)}"

@mcp.tool()
def find_similar_passages(reference_text: str, n_results: int = 5) -> str:
    """Find passages similar to a given text (clustering optimized).
    
    Args:
        reference_text: The reference text to find similar passages for
        n_results: Number of similar passages to return (default: 5, max: 10)
    
    Returns:
        Similar passages with similarity scores and content
    """
    if not collection:
        return "❌ Gospel search not initialized. Please check the server setup."
    
    n_results = min(n_results, 10)
    
    try:
        results = search_gospel_embeddings(reference_text, "clustering", n_results)
        
        response = f"🔗 **Similar Passages to:** {reference_text[:100]}...\n\n"
        for result in results:
            response += f"**{result['rank']}. Similarity: {result['similarity_score']} | Chunk {result['chunk_number']}**\n"
            response += f"📖 {result['text']}\n"
            response += "─" * 80 + "\n\n"
        
        return response
        
    except Exception as e:
        return f"❌ Error finding similar passages: {str(e)}"

@mcp.tool()
def get_collection_stats() -> str:
    """Get statistics about the Gospel embeddings collection.
    
    Returns:
        Comprehensive statistics about the database, model, and available tools
    """
    if not collection:
        return "❌ Gospel search not initialized. Please check the server setup."
    
    try:
        stats = {
            'total_chunks': collection.count(),
            'database_path': "/Volumes/d/code/aiml/embeddings/chromadb_storage",
            'model_path': "/Volumes/d/code/aiml/embeddings/models/gemmaembedding",
            'embedding_dimension': 768,
            'collection_name': "gospel_embeddings"
        }
        
        response = f"""📊 **Gospel Embeddings Collection Statistics**

🗂️ **Database Info:**
   • Total Chunks: {stats['total_chunks']:,}
   • Collection: {stats['collection_name']}
   • Database Path: {stats['database_path']}

🤖 **Model Info:**
   • Model: EmbeddingGemma (Google)
   • Path: {stats['model_path']}
   • Embedding Dimension: {stats['embedding_dimension']}
   • Task Optimization: Enabled

📚 **Content:**
   • Source: The Gospel of Sri Ramakrishna
   • Processing: Cleaned text, 500-char chunks, 100-char overlap
   • Prompt Format: Document embeddings with 'title: none | text: {{content}}'

🔧 **Available Tools:**
   • search_gospel - General semantic search
   • ask_question - Q&A optimized search  
   • verify_teaching - Fact-checking search
   • get_context - Get surrounding chunks
   • find_similar_passages - Find related content
   • get_collection_stats - This information
"""
        
        return response
        
    except Exception as e:
        return f"❌ Error getting stats: {str(e)}"

if __name__ == "__main__":
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Gospel Search MCP Server")
    parser.add_argument(
        "--transport", 
        choices=["stdio", "http"], 
        default="stdio",
        help="Transport protocol to use (default: stdio)"
    )
    parser.add_argument(
        "--host", 
        default="localhost", 
        help="Host to bind HTTP server to (default: localhost)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=8000, 
        help="Port to bind HTTP server to (default: 8000)"
    )
    
    args = parser.parse_args()
    
    if args.transport == "http":
        print(f"🌐 Starting HTTP server on http://{args.host}:{args.port}")
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        print("📡 Starting STDIO server (for MCP clients)")
        mcp.run()
