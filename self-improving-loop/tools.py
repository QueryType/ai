"""
tools.py — Web search utilities via Tavily.

Mirrors the Lipi pattern: TavilyClient loaded lazily from TAVILY_API_KEY env var.
Used by the loop's pre-search step (--search flag) to ground the generator
with real web context before the generate phase.
"""

import os
from datetime import datetime

_client = None


def get_system_date(fmt: str = "%A, %B %d, %Y") -> str:
    """Return the real current date from the local system clock."""
    return datetime.now().strftime(fmt)


def _tavily():
    global _client
    if _client is None:
        from tavily import TavilyClient
        key = os.environ.get("TAVILY_API_KEY", "")
        if not key:
            raise RuntimeError(
                "TAVILY_API_KEY not set. Export it or add to your shell env."
            )
        _client = TavilyClient(api_key=key)
    return _client


def web_search(
    query: str,
    num_results: int = 8,
    search_depth: str = "basic",
    topic: str = "general",
    include_answer: bool = True,
) -> str:
    """
    Search the web via Tavily. Returns formatted text ready to inject as context.

    search_depth: "basic" (fast, 1 credit) | "advanced" (deeper, 2 credits)
    topic:        "general" | "news"
    """
    try:
        resp = _tavily().search(
            query=query,
            max_results=num_results,
            search_depth=search_depth,
            topic=topic,
            include_answer=include_answer,
        )
    except Exception as e:
        return f"[Tavily search error: {e}]"

    lines = []
    if include_answer and resp.get("answer"):
        lines.append(f"Summary: {resp['answer']}\n")

    for r in resp.get("results", []):
        title   = r.get("title", "")
        url     = r.get("url", "")
        content = r.get("content", "").strip()
        score   = r.get("score", 0)
        lines.append(f"• {title}\n  {content[:400]}\n  {url}  [score={score:.2f}]")

    return "\n\n".join(lines) if lines else "[No results returned]"


def fetch_url(url: str, max_chars: int = 6000) -> str:
    """Fetch and clean a URL's content via Tavily Extract."""
    try:
        resp = _tavily().extract(urls=[url])
        results = resp.get("results", [])
        if not results:
            return f"[Tavily extract: no content for {url}]"
        raw = results[0].get("raw_content", "") or results[0].get("content", "")
        text = raw.strip()
        if len(text) > max_chars:
            half = max_chars // 2
            text = text[:half] + f"\n\n[... {len(text)-max_chars} chars truncated ...]\n\n" + text[-half:]
        return text
    except Exception as e:
        return f"[Tavily extract error: {e}]"
