"""Configuration for Story Chunker."""

import os

# Chunking settings
NO_CHUNK_SIZE = 2000  # If file is smaller than this, don't chunk
CHUNK_SIZE = 1000  # Size of each chunk in characters
PARALLEL = 5  # Number of concurrent LLM requests (min 1, match to LLM server slots)

# LLM settings - using OpenAI SDK
LLM_CONFIG = {
    "base_url": os.getenv("LLM_BASE_URL", "http://localhost:8080/v1"),
    "api_key": os.getenv("LLM_API_KEY", "lm-studio"),
    "model": os.getenv("LLM_MODEL", "your-model-name"),
    "temperature": 0.3,
    "max_tokens": 1000,
}

# System prompt for subject detection
SYSTEM_PROMPT = """You are a text analysis assistant. Your task is to determine if the given text chunk contains information about any of the specified subjects/topics/genre.

Respond with ONLY a JSON object in this format:
{"matches": ["subject1", "subject2"]}

If no subjects match, return:
{"matches": []}

Be thorough but accurate. Only mark a subject as matching if it's clearly matching the description or essence of the subject in the text."""
