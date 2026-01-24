"""
Configuration for the Story Summarizer system.

Contains model configuration, constants, and settings.
"""

from strands.models.openai import OpenAIModel
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# If every thing fails, use this default context limit
DEFAULT_MODEL_CONTEXT_LIMIT = 4 * 1024  # 4096 tokens
LOCAL_BASE = "http://10.0.0.4:8080"
LOCAL_BASE_URL = f"{LOCAL_BASE}/v1"
API_KEY = "not-needed-for-local-testing"

# Configure the OpenAI model hosted on a local server
llm_model = OpenAIModel(
    client_args={
        "base_url": LOCAL_BASE_URL ,  # Local OpenAI API server
        "api_key": API_KEY,
    },
    model_id="mistralai/magistral-small-2509",
    params={
        "max_tokens": 10240,
        "temperature": 0.7,
    }
)

# Alternative configuration (RunPod)
# Uncomment to use RunPod instead of local server
'''
llm_model = OpenAIModel(
    client_args={
        "base_url": "https://api.runpod.ai/v2/r47gpaq8tuz0uk/openai/v1",
        "api_key": os.getenv("RUN_POD_API_KEY"),
    },
    model_id="mistralai/mistral-small-3.2-24b-instruct-2506",
    params={
        "max_tokens": 10240,
        "temperature": 0.7,
    }
)
'''
