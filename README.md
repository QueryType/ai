# AI Projects Collection

A collection of AI-powered applications and tools built with Python, spanning interactive fiction, conversational AI, image generation, semantic search, and more.

## Interactive Fiction & Storytelling

### [Game Master](./game-master)
AI-driven text adventure engine replicating KoboldCPP's Adventure mode. Declare actions, the GM narrates consequences in streaming prose with dice rolls and persistent memory. Terminal and web UI. Supports vision-capable models for in-game images.

### [Story Engine](./story-engine)
Multi-agent narrative engine that writes roleplay and adventure fiction from structured scene files. A pipeline of agents (LoreInjector, Narrator, Evaluator, Summariser) generates prose beat-by-beat with quality gating. Autonomous, interactive, and semi-interactive modes.

### [Story Summarizer](./story_summarizer)
Multi-agent workflow for intelligent story summarization. Sequential agents handle character analysis, content/tone analysis, summary generation, and title creation.

### [Story Chunker](./story_chunker)
Extract specific topics, themes, or subjects from story files using AI. Useful for researchers and writers working with large text files.

## Conversational AI

### [Chat Engine](./chat-engine)
CLI tool for multi-character autonomous conversation. Multiple AI characters share a world and talk to each other. Watch, steer, or step in as any character at any time. Supports rule-based and LLM-driven turn selection.

### [Dual Agent Chat](./dual-agent-chat)
Lightweight system for conversations between two AI agents with role-switching memory optimization. Configuration-driven with OpenAI-compatible API support and interactive controls.

### [Faaltoo Chat](./faaltoo-chat)
Zero-friction local LLM chat launcher. Pick dimension chips (archetype, mood, talk-type) and jump into a conversation — no character cards or world-building needed. Web and terminal UI.

## Image Generation & Vision

### [BFL Kontext Suite](./bfl)
Python toolkit for AI image generation and editing using the Black Forest Labs Kontext API. Text-to-image generation, image editing, interactive CLI, and Gradio web UI.

### [Llama Server Multimodal](./llama-server-multimodal)
Image analyzer and tagger using OpenAI-compatible vision APIs. Multiple tagging styles: descriptions, booru-style tags, NSFW classification, artistic analysis.

### [Real-time Webcam & Screen Capture](./rt_webcam_scr)
Web-based interface for real-time vision model analysis using webcam or screen capture. Frame skipping, performance metrics, and advanced logging.

### [HF Inference](./hf_inference)
Gradio apps for Hugging Face Inference API — text chat (multi-model) and text-to-image generation (FLUX.1).

## Search & Knowledge

### [Gospel Embeddings](./gospel_embeddings)
Semantic search for The Gospel of Sri Ramakrishna using EmbeddingGemma, ChromaDB, and MCP. 7,862 text chunks with advanced semantic search.

### [YouTube Searcher MCP](./yt_searcher_mcp)
LLM-powered search pipeline with MCP server. Intent analysis, Google search, web scraping, YouTube query generation, and video search.

### [MCP Tools](./mcp)
Programs and utilities built on the Model Context Protocol for AI agent integration.

## Language & Audio

### [MymicroGPT](./mymicroGPT)
Pure Python, zero-dependency GPT that learns Devanagari character patterns from Indian names and generates new Sanskrit/Hindi names. Custom autograd engine, character-level tokenizer, ~32K name dataset.

### [TTS Krutrim](./tts_krutrim)
Web app using Krutrim's TTS API for text-to-speech. Built with Gradio, supporting English and Hindi with multiple speaker voices.

## Getting Started

Each project contains its own README with setup and usage instructions. Most projects follow a simple pattern:

```bash
cd <project>
pip install -r requirements.txt  # or conda, see project README
cp .env.example .env             # configure API keys / model endpoints
```

## Requirements

- Python 3.10+
- API keys or local LLM servers depending on the project (see individual READMEs)
- Project-specific dependencies installed per-project