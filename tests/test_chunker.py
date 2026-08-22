"""
Tests for backend/app/ingestion/chunker.py

Run with:  pytest tests/test_chunker.py -v
Requires:  pip install tree-sitter-language-pack pytest
"""
import pytest
from backend.app.ingestion.chunker import chunk_file, _estimate_tokens, TOKEN_LIMIT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_chunk_by_symbol(chunks: list[dict], name: str) -> dict | None:
    return next((c for c in chunks if c.get("symbol_name") == name), None)


# ---------------------------------------------------------------------------
# 1. Function signature is never separated from its body
# ---------------------------------------------------------------------------

PYTHON_SIMPLE_FUNCTION = """\
def greet(name: str) -> str:
    \"\"\"Return a greeting string.\"\"\"
    message = f"Hello, {name}!"
    return message
"""

def test_function_signature_stays_with_body():
    chunks = chunk_file("greet.py", PYTHON_SIMPLE_FUNCTION, "python")
    assert len(chunks) >= 1
    greet_chunk = _find_chunk_by_symbol(chunks, "greet")
    assert greet_chunk is not None, "Expected a chunk with symbol_name='greet'"
    # The def line and the return statement must be in the same chunk
    assert "def greet" in greet_chunk["content"]
    assert "return message" in greet_chunk["content"]
    # start_line should point to the def line (line 1)
    assert greet_chunk["start_line"] == 1


# ---------------------------------------------------------------------------
# 2. A large class gets split into per-method chunks
# ---------------------------------------------------------------------------

def _make_large_class(n_methods: int, lines_per_method: int = 20) -> str:
    """Generate a Python class with n_methods methods, each ~lines_per_method lines."""
    body_line = '        x = x + 1  # padding\n'
    methods = []
    for i in range(n_methods):
        body = body_line * lines_per_method
        methods.append(
            f"    def method_{i}(self, x: int) -> int:\n"
            f"        \"\"\"Method {i} docstring.\"\"\"\n"
            f"{body}"
            f"        return x\n"
        )
    return "class BigClass:\n" + "".join(methods)


def test_large_class_splits_into_per_method_chunks():
    # 12 methods × ~22 lines each => the class as a whole far exceeds TOKEN_LIMIT
    code = _make_large_class(n_methods=12, lines_per_method=22)
    chunks = chunk_file("big.py", code, "python")
    method_chunks = [c for c in chunks if c.get("symbol_name", "").startswith("method_")]
    # We expect most methods to appear as distinct chunks
    assert len(method_chunks) >= 10, (
        f"Expected ≥10 method chunks for a large class, got {len(method_chunks)}"
    )
    # Each method chunk should be within the token limit (or close – we allow some slack
    # because a very long single method has no sub-chunkable children)
    for chunk in method_chunks:
        tokens = _estimate_tokens(chunk["content"])
        assert tokens <= TOKEN_LIMIT * 1.5, (
            f"Chunk '{chunk['symbol_name']}' has {tokens} tokens, expected ≤{TOKEN_LIMIT * 1.5}"
        )


# ---------------------------------------------------------------------------
# 3. Tiny functions are merged rather than producing one chunk per function
# ---------------------------------------------------------------------------

MANY_TINY_FUNCTIONS = "\n".join(
    f"def tiny_{i}(x):\n    return x + {i}\n"
    for i in range(20)
)

def test_tiny_functions_are_merged():
    chunks = chunk_file("tiny.py", MANY_TINY_FUNCTIONS, "python")
    # 20 tiny functions (each ~2 lines / ~6 tokens) should be merged into
    # far fewer chunks.  With a 400-token budget each merged chunk can hold
    # many tiny functions, so we expect well under 10 total chunks.
    # If this assertion fails, the merge logic is broken or disabled.
    assert len(chunks) < 10, (
        f"Expected < 10 merged chunks for 20 tiny functions, got {len(chunks)}"
    )
    # All returned chunks must be non-empty
    for c in chunks:
        assert c["content"].strip() != ""


# ---------------------------------------------------------------------------
# 4. Syntax error falls back to sliding-window without crashing
# ---------------------------------------------------------------------------

BROKEN_PYTHON = """\
def good_function():
    return 42

def broken_function(
    # Missing closing paren and body — deliberate syntax error
    x = 1 +

class AlsoFine:
    pass
"""

def test_syntax_error_fallback():
    # Should not raise; should return sliding-window chunks with symbol_name=None
    chunks = chunk_file("broken.py", BROKEN_PYTHON, "python")
    assert isinstance(chunks, list)
    assert len(chunks) >= 1
    # All chunks from the fallback path must have symbol_name=None
    for c in chunks:
        assert c["symbol_name"] is None, (
            f"Expected symbol_name=None for fallback chunk, got '{c['symbol_name']}'"
        )
    # Content from the original file must appear somewhere in the chunks
    all_content = "\n".join(c["content"] for c in chunks)
    assert "good_function" in all_content


# ---------------------------------------------------------------------------
# 5. JavaScript function chunk has correct symbol name and line numbers
# ---------------------------------------------------------------------------

JS_CODE = """\
function add(a, b) {
    return a + b;
}

function multiply(a, b) {
    return a * b;
}
"""

def test_javascript_function_chunks():
    chunks = chunk_file("math.js", JS_CODE, "javascript")
    add_chunk = _find_chunk_by_symbol(chunks, "add")
    multiply_chunk = _find_chunk_by_symbol(chunks, "multiply")
    assert add_chunk is not None, "Expected chunk for 'add'"
    assert multiply_chunk is not None, "Expected chunk for 'multiply'"
    assert add_chunk["start_line"] == 1
    assert multiply_chunk["start_line"] > add_chunk["end_line"]


# ---------------------------------------------------------------------------
# 6. Unknown / unsupported language falls back gracefully
# ---------------------------------------------------------------------------

def test_unsupported_language_fallback():
    chunks = chunk_file("foo.cobol", "IDENTIFICATION DIVISION.\nPROGRAM-ID. HELLO.", "cobol")
    assert isinstance(chunks, list)
    assert len(chunks) >= 1
    for c in chunks:
        assert c["symbol_name"] is None


# ---------------------------------------------------------------------------
# 7. Line numbers are contiguous and sane across all chunks
# ---------------------------------------------------------------------------

PYTHON_MULTI_FUNC = """\
def alpha():
    return 1

def beta():
    return 2

def gamma():
    return 3
"""

def test_line_numbers_are_sane():
    chunks = chunk_file("multi.py", PYTHON_MULTI_FUNC, "python")
    assert len(chunks) >= 1
    for c in chunks:
        assert c["start_line"] >= 1
        assert c["end_line"] >= c["start_line"]
