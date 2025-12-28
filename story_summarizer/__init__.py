"""
Story Summarizer Package

A multi-agent workflow system for intelligent story summarization using Strands Agents SDK.
Uses a sequential workflow pattern where each agent hands off to the next with full context.
"""

from .story_summarizer import (
    summarize_story,
    character_analyst,
    content_analyst,
    summary_generator
)

__version__ = "1.0.0"
__all__ = ["summarize_story", "character_analyst", "content_analyst", "summary_generator"]
