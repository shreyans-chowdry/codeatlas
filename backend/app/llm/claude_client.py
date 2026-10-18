"""
Claude LLM client for CodeAtlas AI.

Provides prompt construction and streaming answer generation using
the Anthropic Claude API.
"""
import os
import logging
from typing import AsyncGenerator

import anthropic

logger = logging.getLogger(__name__)

# Model to use. Override via CLAUDE_MODEL env var (any current Claude model id works).
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = """\
You are CodeAtlas AI, an expert code-understanding assistant.
You have been given a set of code excerpts retrieved from a specific GitHub \
repository. Your job is to answer the user's question about that codebase.

You MUST follow these rules at all times:

1. **Answer only from the provided context.** Do not use any knowledge about \
the codebase that is not present in the code excerpts below. Do not invent \
APIs, functions, or behaviors.

2. **Acknowledge insufficient context.** If the retrieved excerpts do not \
contain enough information to answer the question confidently, say so \
clearly and explicitly — e.g. "The provided context does not contain enough \
information to answer this question." Never guess or hallucinate.

3. **Cite your sources.** For every factual claim you make about the code, \
cite the specific file path (and line range where relevant) using this \
format: `auth/middleware.py (lines 12–40)`. If a claim spans multiple \
files, cite all of them.

4. **Be precise and technical.** Your audience is a software engineer \
exploring the codebase. Use exact function names, class names, and \
variable names as they appear in the code.
"""


def build_prompt(question: str, chunks: list[dict]) -> str:
    """
    Assembles the user-turn content: the retrieved code context followed
    by the user's question.

    Each chunk is labeled with its file path and line range so Claude can
    cite them precisely:

        ### auth/middleware.py (lines 12-40)
        ```python
        def verify_token(token: str) -> bool:
            ...
        ```

    The system prompt (with citation and grounding rules) is kept separate
    so it can be passed as the Anthropic ``system`` parameter.
    """
    if not chunks:
        raise ValueError("build_prompt() called with an empty chunks list — caller must handle this.")

    lines: list[str] = ["## Retrieved Code Context\n"]

    for chunk in chunks:
        file_path = chunk.get("file_path") or chunk.get("path") or "unknown"
        start = chunk.get("start_line", "?")
        end = chunk.get("end_line", "?")
        content = chunk.get("content", "").strip()

        lines.append(f"### {file_path} (lines {start}-{end})")
        lines.append(f"```\n{content}\n```")
        lines.append("")  # blank line between chunks

    lines.append("---")
    lines.append(f"## Question\n\n{question}")

    return "\n".join(lines)


async def stream_answer(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Calls the Anthropic Claude API with streaming enabled.
    Yields text deltas as they arrive from the API.

    Uses the prompt from ``build_prompt()`` as the user turn, and the
    module-level SYSTEM_PROMPT as the system turn so that grounding and
    citation rules are always enforced.
    """
    user_content = build_prompt(question, chunks)

    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Prior turns (plain text, no code context) give follow-up questions continuity.
    # The API requires alternating roles starting with "user", so normalise first.
    messages: list[dict] = []
    for turn in history or []:
        role, content = turn.get("role"), (turn.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if not messages and role != "user":
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n\n" + content
        else:
            messages.append({"role": role, "content": content})
    if messages and messages[-1]["role"] == "user":
        messages.pop()  # unanswered question (e.g. stream was interrupted)
    messages.append({"role": "user", "content": user_content})

    async with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        async for text_delta in stream.text_stream:
            yield text_delta
