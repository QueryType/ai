"""
LLM client for dual agent chat system.
Handles communication with OpenAI-compatible API endpoints.
"""

import requests
import time
from typing import List, Dict, Any, Optional


class LLMClient:
    """Client for interacting with OpenAI-compatible LLM APIs."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the LLM client.
        
        Args:
            config: LLM configuration dictionary from app.json
        """
        self.api_base_url = config['api_base_url'].rstrip('/')
        self.api_key = config.get('api_key', 'not-needed')
        self.model = config['model']
        self.temperature = config.get('temperature', 0.8)
        self.max_tokens = config.get('max_tokens', 200)
        self.top_p = config.get('top_p', 0.95)
        self.frequency_penalty = config.get('frequency_penalty', 0.0)
        self.presence_penalty = config.get('presence_penalty', 0.0)
        
        # Request settings
        self.timeout = config.get('timeout', 60)
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 2)
    
    def chat_completion(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """
        Send a chat completion request to the LLM API.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            
        Returns:
            The assistant's response text, or None if failed
        """
        endpoint = f"{self.api_base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": False
        }
        
        # Try with retries
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    assistant_message = result['choices'][0]['message']['content']
                    return assistant_message.strip()
                else:
                    print(f"⚠️  API returned status {response.status_code}: {response.text}")
                    if attempt < self.max_retries - 1:
                        print(f"   Retrying in {self.retry_delay} seconds...")
                        time.sleep(self.retry_delay)
                    
            except requests.exceptions.Timeout:
                print(f"⚠️  Request timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    
            except requests.exceptions.ConnectionError:
                print(f"⚠️  Connection error (attempt {attempt + 1}/{self.max_retries})")
                print(f"   Make sure LLM server is running at {self.api_base_url}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    
            except Exception as e:
                print(f"⚠️  Unexpected error: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
        
        print("❌ Failed to get response after all retries")
        return None
    
    def test_connection(self) -> bool:
        """
        Test the connection to the LLM API.
        
        Returns:
            True if connection successful, False otherwise
        """
        print(f"Testing connection to {self.api_base_url}...")
        
        test_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"}
        ]
        
        response = self.chat_completion(test_messages)
        
        if response:
            print("✅ Connection successful!")
            print(f"   Response: {response[:100]}...")
            return True
        else:
            print("❌ Connection failed")
            return False


# Test function
if __name__ == "__main__":
    print("Testing LLMClient...")
    print("="*60)
    
    # Test configuration
    test_config = {
        "api_base_url": "http://localhost:1234/v1",
        "api_key": "not-needed",
        "model": "local-model",
        "temperature": 0.7,
        "max_tokens": 100,
        "top_p": 0.95
    }
    
    client = LLMClient(test_config)
    
    print("\nAttempting to test connection...")
    print("(This will fail if no LLM server is running)")
    print("-"*60)
    
    client.test_connection()
    
    print("\n" + "="*60)
    print("Note: Start an LLM server (e.g., LM Studio) to test fully")
    print("="*60)
