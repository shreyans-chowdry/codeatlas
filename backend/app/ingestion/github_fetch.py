import re
from git import Repo, exc

def clone_repo(github_url: str, dest_dir: str):
    """
    Clones a public GitHub repository into the specified destination directory.
    Performs a shallow clone (depth=1).
    """
    # Simple validation for a github.com URL
    if not re.match(r'^https?://(www\.)?github\.com/[\w.-]+/[\w.-]+/?$', github_url):
        raise ValueError(f"Invalid GitHub URL: {github_url}")
    
    try:
        Repo.clone_from(github_url, dest_dir, depth=1)
    except exc.GitCommandError as e:
        raise RuntimeError(f"Failed to clone repository. Ensure it exists and is public: {e}")
