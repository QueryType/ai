"""
Utility functions for the Story Summarizer system.

Contains helper functions for model configuration and summarization logic.
"""
import json
import requests
from .config import DEFAULT_MODEL_CONTEXT_LIMIT
from .config import LOCAL_BASE, LOCAL_BASE_URL


# Get model context limit, trying LM Studio and llama.cpp endpoints
def get_model_context_limit():
    """Get context limit from LM Studio, llama.cpp, or default to 32K"""
    
    # Try LM Studio first
    try:
        response = requests.get(f"{LOCAL_BASE}/api/v0/models", timeout=1)
        data = response.json()
        for m in data.get("data", []):
            if m.get("max_context_length"):
                print(f"Model context limit obtained from LM Studio. {m['max_context_length']}")
                return m["max_context_length"]
    except:
        pass
    
    # Try llama.cpp
    try:
        print("Trying to get model context limit from llama.cpp...")
        response = requests.get(f"{LOCAL_BASE}/props", timeout=10)
        data = json.loads(response.text)
        n_ctx = data['default_generation_settings']['n_ctx']
        if n_ctx:
            print(f"Model context limit obtained from llama.cpp. {n_ctx}")
            return n_ctx
    except:
        pass
    
    # Default fallback
    print(f"Falling back to default model context limit: {DEFAULT_MODEL_CONTEXT_LIMIT}")
    return DEFAULT_MODEL_CONTEXT_LIMIT
        


def estimate_token_count(text: str) -> int:
    """
    Estimate the number of tokens in a string by querying the local LLM server.
    
    Args:
        text: The text string to count tokens for
    
    Returns:
        int: Number of tokens according to the local model's tokenizer
        
    Notes:
        - Queries the local LLM server (LM Studio or llama.cpp) for accurate token count
        - Falls back to word count * 1.3 approximation if server is unavailable
    """
    # Try LM Studio tokenize endpoint
    try:
        response = requests.post(
            f"{LOCAL_BASE_URL}/completions",
            json={
                "prompt": text,
                "max_tokens": 0,  # Don't generate, just tokenize
                "echo": False
            },
            timeout=2
        )
        if response.status_code == 200:
            data = response.json()
            # Check if usage info is returned
            if "usage" in data and "prompt_tokens" in data["usage"]:
                token_count = data["usage"]["prompt_tokens"]
                print(f"Token count obtained from LM Studio endpoint. {token_count}")
                return token_count
    except:
        pass
    
    # Try llama.cpp tokenize endpoint
    try:
        response = requests.post(
            f"{LOCAL_BASE}/tokenize",
            json={"content": text},
            timeout=2
        )
        if response.status_code == 200:
            data = response.json()
            if "tokens" in data:
                token_count = len(data["tokens"])
                print(f"Token count obtained from llama.cpp endpoint. {token_count}")
                return token_count  
    except:
        pass
    
    # Fallback approximation
    word_count = len(text.split())
    print("Falling back to word count approximation for token count.")
    return int(word_count * 1.3)


def determine_summarization_strength(original_word_count, target_words):
    """
    Determine the appropriate summarization strength based on story length.
    
    Args:
        original_word_count: Number of words in the original story
        target_words: Target word count for the summary
        
    Returns:
        tuple: (strength_name, strength_description, adjusted_target)
            - strength_name: "NONE", "LIGHT", "MEDIUM", or "HEAVY"
            - strength_description: Description for the summary generator
            - adjusted_target: Adjusted target word count
    """
    # If story is already shorter than or equal to target, no summarization needed
    if original_word_count <= target_words:
        return ("NONE", "No summarization needed - preserve entire story", original_word_count)
    
    ratio = original_word_count / target_words
    
    # Light summarization: story is 1-1.4x target (e.g., 3000-4200 words for 3000 target)
    # Aim for ~10% reduction, so target is 90% of original
    if ratio <= 1.4:
        adjusted_target = int(original_word_count * 0.9)
        return ("LIGHT", 
                "Apply LIGHT summarization (TARGET: 10% reduction only). Your output MUST be approximately 90% of the original length. Preserve nearly all details, remove only redundant descriptions and minor tangents. Keep most dialogue and scene descriptions. DO NOT over-compress - this is MINIMAL editing.",
                adjusted_target)
    
    # Medium summarization: story is 1.4-2.3x target (e.g., 4200-7000 words for 3000 target)
    # Aim for ~40% reduction, bringing it closer to target
    elif ratio <= 2.3:
        adjusted_target = int(original_word_count * 0.6)
        return ("MEDIUM",
                "Apply MEDIUM summarization (TARGET: 40% reduction). Your output MUST be approximately 60% of the original length. Condense scenes while keeping key moments, important dialogue, and character interactions. Remove subplot details that don't affect main narrative.",
                adjusted_target)
    
    # Heavy summarization: story is >2.3x target (e.g., >7000 words for 3000 target)
    # Aggressive reduction to meet target
    else:
        adjusted_target = target_words
        return ("HEAVY",
                "Apply HEAVY summarization (TARGET: aggressive reduction to specified word count). Your output MUST be approximately the target word count specified. Focus on core plot points and essential character moments. Aggressively condense while preserving story essence and critical turning points.",
                adjusted_target)
