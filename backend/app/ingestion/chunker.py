"""
AST-aware code chunker using tree-sitter.

Uses tree-sitter-language-pack for prebuilt grammars. Falls back to a
sliding-window chunker if a grammar is unavailable or the file fails to parse.
"""
from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKEN_LIMIT = 400          # approximate token budget per chunk
MERGE_THRESHOLD = 200      # chunks below this size may be merged with the next
SLIDING_WINDOW_TOKENS = 350
SLIDING_OVERLAP_TOKENS = 50

# Tree-sitter node types that represent standalone "chunkable" symbols,
# keyed by the canonical language name used by tree-sitter-language-pack.
CHUNKABLE_NODES: dict[str, set[str]] = {
    "python": {
        "function_definition",
        "async_function_definition",
        "class_definition",
    },
    "javascript": {
        "function_declaration",
        "function_expression",
        "arrow_function",
        "class_declaration",
        "export_statement",
        "lexical_declaration",  # const / let at top level
    },
    "typescript": {
        "function_declaration",
        "function_signature",
        "arrow_function",
        "class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "export_statement",
        "lexical_declaration",
    },
    "java": {
        "class_declaration",
        "interface_declaration",
        "method_declaration",
        "constructor_declaration",
        "enum_declaration",
    },
    "go": {
        "function_declaration",
        "method_declaration",
        "type_declaration",
    },
    "rust": {
        "function_item",
        "impl_item",
        "struct_item",
        "enum_item",
        "trait_item",
    },
    "c": {
        "function_definition",
        "declaration",
    },
    "cpp": {
        "function_definition",
        "class_specifier",
        "declaration",
    },
    "ruby": {
        "method",
        "class",
        "module",
        "singleton_method",
    },
}

# Node types that contain a "name" child with the symbol's identifier
NAME_EXTRACTORS: dict[str, str] = {
    # tree-sitter node type  -> field name holding the identifier
    "function_definition": "name",
    "async_function_definition": "name",
    "class_definition": "name",
    "function_declaration": "name",
    "class_declaration": "name",
    "interface_declaration": "name",
    "method_declaration": "name",
    "constructor_declaration": "name",
    "enum_declaration": "name",
    "type_alias_declaration": "name",
    "function_item": "name",
    "impl_item": "name",       # the type being implemented
    "struct_item": "name",
    "enum_item": "name",
    "trait_item": "name",
    "function_signature": "name",
    "method": "name",
    "class": "name",
    "module": "name",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """
    Approximate token count using whitespace-split word count.
    Avoids importing a full tokenizer for performance.
    """
    return len(re.split(r"\s+", text.strip()))


def _get_symbol_name(node) -> Optional[str]:
    """Extract the identifier/symbol name from a tree-sitter node, if available."""
    field = NAME_EXTRACTORS.get(node.type)
    if field:
        child = node.child_by_field_name(field)
        if child:
            return child.text.decode("utf-8", errors="replace")
    return None


def _lines_from_node(node, content_bytes: bytes) -> tuple[int, int, str]:
    """Return (start_line, end_line, text) from a tree-sitter node (1-indexed)."""
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    text = content_bytes[node.start_byte: node.end_byte].decode("utf-8", errors="replace")
    return start_line, end_line, text


# ---------------------------------------------------------------------------
# Sliding-window fallback
# ---------------------------------------------------------------------------

def _sliding_window_chunks(content: str) -> list[dict]:
    """
    Plain sliding-window chunker over raw text lines.
    Used when AST parsing is unavailable or fails.
    Each chunk has symbol_name=None so the retrieval layer can
    deprioritise these vs AST-derived chunks.
    """
    lines = content.splitlines()
    chunks: list[dict] = []
    start = 0
    buf: list[str] = []
    buf_tokens = 0

    for i, line in enumerate(lines):
        line_tokens = _estimate_tokens(line)
        buf.append(line)
        buf_tokens += line_tokens

        if buf_tokens >= SLIDING_WINDOW_TOKENS:
            chunk_content = "\n".join(buf)
            chunks.append({
                "content": chunk_content,
                "symbol_name": None,
                "start_line": start + 1,
                "end_line": start + len(buf),
            })
            # Overlap: keep the last SLIDING_OVERLAP_TOKENS worth of lines
            overlap_lines: list[str] = []
            overlap_tokens = 0
            for l in reversed(buf):
                lt = _estimate_tokens(l)
                if overlap_tokens + lt > SLIDING_OVERLAP_TOKENS:
                    break
                overlap_lines.insert(0, l)
                overlap_tokens += lt
            start = start + len(buf) - len(overlap_lines)
            buf = overlap_lines
            buf_tokens = overlap_tokens

    # Flush remaining lines
    if buf:
        chunks.append({
            "content": "\n".join(buf),
            "symbol_name": None,
            "start_line": start + 1,
            "end_line": start + len(buf),
        })

    return chunks


# ---------------------------------------------------------------------------
# AST chunking
# ---------------------------------------------------------------------------

def _ast_chunks_from_nodes(nodes: list, content_bytes: bytes, chunkable: set[str]) -> list[dict]:
    """
    Recursively convert a list of tree-sitter nodes into chunk dicts,
    splitting oversized nodes at child boundaries and merging tiny siblings.
    """
    raw: list[dict] = []

    for node in nodes:
        start_line, end_line, text = _lines_from_node(node, content_bytes)
        tokens = _estimate_tokens(text)
        symbol_name = _get_symbol_name(node)

        if tokens > TOKEN_LIMIT:
            # Oversized: try to split at chunkable children (e.g. methods inside a class)
            chunkable_children = [
                c for c in node.children if c.type in chunkable and not c.is_missing
            ]
            if chunkable_children:
                raw.extend(_ast_chunks_from_nodes(chunkable_children, content_bytes, chunkable))
                continue
            # No chunkable children — emit as-is (better than truncating)

        raw.append({
            "content": text,
            "symbol_name": symbol_name,
            "start_line": start_line,
            "end_line": end_line,
        })

    # Merge consecutive tiny chunks to reduce excessive fragmentation.
    # When two small adjacent chunks are combined the result spans multiple
    # symbols, so we clear symbol_name (the retrieval layer can still do
    # keyword/embedding search over the merged text).
    merged: list[dict] = []
    for chunk in raw:
        if (
            merged
            and _estimate_tokens(merged[-1]["content"]) < MERGE_THRESHOLD
            and _estimate_tokens(merged[-1]["content"]) + _estimate_tokens(chunk["content"]) <= TOKEN_LIMIT
        ):
            prev = merged[-1]
            prev["content"] = prev["content"] + "\n" + chunk["content"]
            prev["end_line"] = chunk["end_line"]
            # A merged chunk covers multiple symbols — drop the individual name
            prev["symbol_name"] = None
        else:
            merged.append(chunk)

    return merged


def _get_parser_and_chunkable(language: str):
    """
    Attempt to load a tree-sitter parser for the given language via
    tree-sitter-language-pack. Returns (parser, chunkable_node_types) or
    (None, None) if unavailable.
    """
    try:
        from tree_sitter_language_pack import get_parser  # type: ignore
        parser = get_parser(language)
        chunkable = CHUNKABLE_NODES.get(language, set())
        return parser, chunkable
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_file(file_path: str, content: str, language: str) -> list[dict]:
    """
    Parse a source file and return a list of chunk dicts, each containing:
      - content (str)
      - symbol_name (str | None)
      - start_line (int, 1-indexed)
      - end_line (int, 1-indexed)

    Falls back to sliding-window chunking if the language grammar is
    unavailable or the file contains syntax errors.
    """
    parser, chunkable = _get_parser_and_chunkable(language)

    if parser is None or not chunkable:
        # No grammar available for this language
        return _sliding_window_chunks(content)

    content_bytes = content.encode("utf-8")
    try:
        tree = parser.parse(content_bytes)
    except Exception:
        return _sliding_window_chunks(content)

    if tree.root_node.has_error:
        # Syntax errors detected — fall back to sliding window
        # (has_error is True even for partial errors)
        return _sliding_window_chunks(content)

    # Collect top-level chunkable nodes from the root
    top_level = [
        node
        for node in tree.root_node.children
        if node.type in chunkable and not node.is_missing
    ]

    if not top_level:
        # File has no recognisable top-level symbols (e.g. a script with only
        # expressions) — fall back to sliding window
        return _sliding_window_chunks(content)

    return _ast_chunks_from_nodes(top_level, content_bytes, chunkable)
