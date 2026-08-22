import os

SKIP_DIRS = {"node_modules", ".git", "venv", "__pycache__", "dist", "build", ".next"}
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB

EXT_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".rb": "ruby"
}

def is_binary(file_path: str) -> bool:
    """Check for null bytes in the first 4KB to detect binary files."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(4096)
            if b"\x00" in chunk:
                return True
    except Exception:
        return True  # If unreadable, treat as binary/skip
    return False

def list_source_files(repo_dir: str) -> list[dict]:
    """
    Walks the cloned repo and returns a list of dicts with file path and detected language.
    """
    source_files = []

    for root, dirs, files in os.walk(repo_dir):
        # Modify dirs in-place to skip unwanted directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in EXT_LANGUAGE_MAP:
                continue

            file_path = os.path.join(root, file)

            # Skip large files
            try:
                if os.path.getsize(file_path) > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue

            # Skip binary files
            if is_binary(file_path):
                continue

            rel_path = os.path.relpath(file_path, repo_dir)
            source_files.append({
                "path": rel_path,
                "language": EXT_LANGUAGE_MAP[ext]
            })

    return source_files
