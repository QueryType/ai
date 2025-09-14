import torch
from sentence_transformers import SentenceTransformer
import chromadb

# Use from local path to load the model repo
model = SentenceTransformer("/Volumes/d/code/aiml/embeddings/models/gemmaembedding")

# Set device to mps if available
device = "mps" if torch.backends.mps.is_available() else "cpu"

# Get the path of the Gospel
data_path = "raw/The_Gospel_of_Sri_Ramakrishna.txt"

def clean_text(text):
    """Clean text by removing table formatting and extra whitespace."""
    import re
    
    # Remove table formatting characters
    text = re.sub(r'\|', '', text)
    
    # Remove excessive whitespace and newlines
    text = re.sub(r'\n\s*\n', '\n', text)  # Replace multiple newlines with single
    text = re.sub(r'[ \t]+', ' ', text)    # Replace multiple spaces with single
    
    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    return '\n'.join(lines)

def create_chunks_with_overlap(text, chunk_size=500, overlap=100):
    """
    Split text into overlapping chunks of specified size.
    
    Args:
        text: The input text to chunk
        chunk_size: Target size of each chunk in characters
        overlap: Number of characters to overlap between chunks
    
    Returns:
        List of text chunks
    """
    chunks = []
    start = 0
    
    while start < len(text):
        # Calculate end position for this chunk
        end = start + chunk_size
        
        # If this isn't the last chunk, try to break at a sentence or word boundary
        if end < len(text):
            # Look for sentence endings within the last 100 characters of the chunk
            sentence_endings = ['.', '!', '?', '\n\n']
            best_break = end
            
            for i in range(max(0, end - 100), end):
                if text[i] in sentence_endings:
                    best_break = i + 1
            
            # If no sentence ending found, look for word boundaries
            if best_break == end:
                for i in range(end - 50, end):
                    if text[i] == ' ':
                        best_break = i
                        break
            
            end = best_break
        
        # Extract the chunk
        chunk = text[start:end].strip()
        if chunk and len(chunk) > 50:  # Only add chunks with meaningful content
            chunks.append(chunk)
        
        # Move start position for next chunk (with overlap)
        start = end - overlap
        
        # Prevent infinite loop
        if start >= end:
            break
    
    return chunks

# Initialize ChromaDB client with persistent storage
import os
db_path = "chromadb_storage"
if not os.path.exists(db_path):
    os.makedirs(db_path)

client = chromadb.PersistentClient(path=db_path)
print(f"ChromaDB will be stored in: {os.path.abspath(db_path)}")

# Create or get a collection for Gospel embeddings
collection_name = "gospel_embeddings"
try:
    # Try to get existing collection
    collection = client.get_collection(collection_name)
    print(f"Found existing collection '{collection_name}' with {collection.count()} items")
    
    # Ask if user wants to recreate or use existing
    recreate = input("Collection already exists. Recreate it? (y/n): ").lower().startswith('y')
    if recreate:
        client.delete_collection(collection_name)
        collection = client.create_collection(collection_name)
        print(f"Recreated collection '{collection_name}'")
        process_embeddings = True
    else:
        print(f"Using existing collection '{collection_name}'")
        process_embeddings = False
        
except Exception:
    # Collection doesn't exist, create it
    collection = client.create_collection(collection_name)
    print(f"Created new collection '{collection_name}'")
    process_embeddings = True

# Only create embeddings if needed
if process_embeddings or collection.count() == 0:
    # Read the entire file as a single string
    with open(data_path, "r", encoding="utf-8") as f:
        full_text = f.read()

    # Clean the text before chunking
    print("Cleaning text...")
    full_text = clean_text(full_text)

    # Create chunks with overlap
    print("Creating text chunks with overlap...")
    data_list = create_chunks_with_overlap(full_text, chunk_size=500, overlap=100)
    print(f"Created {len(data_list)} chunks from the text")

    # Creating Embeddings for queries with document prompts
    print("Creating embeddings for the Gospel text chunks with optimized prompts...")
    
    # Format each chunk with document prompt
    formatted_chunks = [f'title: none | text: {chunk}' for chunk in data_list]
    docu_embeddings = model.encode(formatted_chunks, device=device)
    print(f"Embeddings shape: {docu_embeddings.shape}")

    # Prepare data for ChromaDB
    # Create unique IDs for each chunk
    ids = [f"chunk_{i}" for i in range(len(data_list))]

    # Prepare metadata with chunk information
    metadatas = [
        {
            "chunk_number": i, 
            "source": "Gospel of Sri Ramakrishna",
            "chunk_length": len(chunk),
            "chunk_start_char": i * 400  # Approximate character position
        } 
        for i, chunk in enumerate(data_list)
    ]

    # Use the chunks directly as documents
    documents = data_list

    # Add embeddings to ChromaDB in batches
    batch_size = 1000  # Safe batch size for ChromaDB
    total_chunks = len(documents)
    
    print(f"Adding {total_chunks} embeddings to ChromaDB in batches of {batch_size}...")
    
    for i in range(0, total_chunks, batch_size):
        end_idx = min(i + batch_size, total_chunks)
        batch_embeddings = docu_embeddings[i:end_idx].tolist()
        batch_ids = ids[i:end_idx]
        batch_metadatas = metadatas[i:end_idx]
        batch_documents = documents[i:end_idx]
        
        collection.add(
            embeddings=batch_embeddings,
            ids=batch_ids,
            metadatas=batch_metadatas,
            documents=batch_documents
        )
        
        print(f"  Added batch {i//batch_size + 1}: chunks {i+1}-{end_idx}")

    print(f"Successfully added all {total_chunks} chunk embeddings to ChromaDB collection '{collection_name}'")
else:
    print(f"Collection already contains {collection.count()} embeddings. Skipping embedding creation.")

# Example: Query the collection
query_text = "What did Ramakrishna say about God?"
print(f"\nSearching for: '{query_text}'")
query_embedding = model.encode([query_text], device=device)

# Search for similar embeddings
results = collection.query(
    query_embeddings=query_embedding.tolist(),
    n_results=3
)

print("\nTop 3 most relevant chunks:")
for i, (doc, distance, metadata) in enumerate(zip(results['documents'][0], results['distances'][0], results['metadatas'][0])):
    print(f"\n{i+1}. Similarity Score: {1-distance:.4f} | Chunk {metadata['chunk_number']}")
    print(f"   Text ({len(doc)} chars): {doc[:200]}...")
    if len(doc) > 200:
        print(f"   ... {doc[-100:]}")
    print("-" * 80)

# Function to search the collection with optimized prompts
def search_gospel(query_text, task_type="search result", n_results=3):
    """
    Search the Gospel collection for relevant passages using optimized prompts.
    
    Args:
        query_text: The search query
        task_type: Task optimization - "search result", "question answering", "fact checking", etc.
        n_results: Number of results to return
    """
    # Format query with task-specific prompt
    formatted_query = f"task: {task_type} | query: {query_text}"
    
    print(f"\nSearching for: '{query_text}'")
    print(f"Task optimization: {task_type}")
    
    query_embedding = model.encode([formatted_query], device=device)
    
    results = collection.query(
        query_embeddings=query_embedding.tolist(),
        n_results=n_results
    )
    
    print(f"\nTop {n_results} most relevant chunks:")
    for i, (doc, distance, metadata) in enumerate(zip(results['documents'][0], results['distances'][0], results['metadatas'][0])):
        print(f"\n{i+1}. Similarity Score: {1-distance:.4f} | Chunk {metadata['chunk_number']}")
        print(f"   Text ({len(doc)} chars):")
        print(f"   {doc}")
        print("-" * 80)

# Test different task optimizations
search_gospel("What did Ramakrishna say about God?", "question answering")
search_gospel("Ramakrishna taught that God dwells in all beings", "fact checking")
search_gospel("meditation and prayer", "search result")
