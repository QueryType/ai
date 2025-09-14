#!/usr/bin/env python3
"""
Test script for Gospel Search MCP Server HTTP mode
"""

import requests
import json
import time

def test_http_server(base_url="http://localhost:8000"):
    """Test the Gospel Search MCP Server in HTTP mode."""
    
    print(f"🧪 Testing Gospel Search MCP Server at {base_url}")
    print("=" * 60)
    
    # Test 1: Server health/info
    print("1️⃣ Testing server connection...")
    try:
        response = requests.get(f"{base_url}/info", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running and accessible")
            print(f"   Response: {response.json()}")
        else:
            print(f"⚠️ Server responded with status {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to connect to server: {e}")
        return
    
    print()
    
    # Test 2: Search Gospel
    print("2️⃣ Testing search_gospel tool...")
    try:
        response = requests.post(
            f"{base_url}/tools/search_gospel",
            json={"query": "God", "n_results": 2},
            timeout=10
        )
        if response.status_code == 200:
            print("✅ search_gospel tool working")
            result = response.json()
            print(f"   Result preview: {str(result)[:200]}...")
        else:
            print(f"❌ search_gospel failed with status {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ search_gospel request failed: {e}")
    
    print()
    
    # Test 3: Ask Question
    print("3️⃣ Testing ask_question tool...")
    try:
        response = requests.post(
            f"{base_url}/tools/ask_question",
            json={"question": "What did Ramakrishna teach about meditation?", "n_results": 2},
            timeout=10
        )
        if response.status_code == 200:
            print("✅ ask_question tool working")
            result = response.json()
            print(f"   Result preview: {str(result)[:200]}...")
        else:
            print(f"❌ ask_question failed with status {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ ask_question request failed: {e}")
    
    print()
    
    # Test 4: Get Collection Stats
    print("4️⃣ Testing get_collection_stats tool...")
    try:
        response = requests.post(
            f"{base_url}/tools/get_collection_stats",
            json={},
            timeout=5
        )
        if response.status_code == 200:
            print("✅ get_collection_stats tool working")
            result = response.json()
            print(f"   Result preview: {str(result)[:300]}...")
        else:
            print(f"❌ get_collection_stats failed with status {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ get_collection_stats request failed: {e}")
    
    print()
    print("🎉 HTTP mode testing complete!")

if __name__ == "__main__":
    import sys
    
    # Allow custom URL as command line argument
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    print("Gospel Search MCP Server - HTTP Mode Tester")
    print(f"Testing server at: {base_url}")
    print("Make sure the server is running with: python gospel_search_server.py --transport http")
    print()
    
    # Wait a moment for user to start server if needed
    input("Press Enter when the server is running...")
    
    test_http_server(base_url)