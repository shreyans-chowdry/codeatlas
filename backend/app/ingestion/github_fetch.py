import os
import re

from git import Repo, exc


def clone_repo(github_url: str, dest_dir: str):
    """
    Clones a GitHub repository into the specified destination directory.
    Performs a shallow clone (depth=1).

    Public repos need nothing. If GITHUB_TOKEN is set, it is used so private
    repos you have access to can be ingested too (and to avoid rate limits).
    """
    if not re.match(r'^https?://(www\.)?github\.com/[\w.-]+/[\w.-]+/?$', github_url):
        raise ValueError(f"Invalid GitHub URL: {github_url}")

    clone_url = github_url
    token = os.getenv("GITHUB_TOKEN")
    if token:
        clone_url = github_url.replace("https://", f"https://x-access-token:{token}@", 1)

    try:
        Repo.clone_from(clone_url, dest_dir, depth=1, env={"GIT_TERMINAL_PROMPT": "0"})
    except exc.GitCommandError as e:
        msg = str(e)
        if token:
            msg = msg.replace(token, "***")
        raise RuntimeError(f"Failed to clone repository. Ensure it exists and is public (or set GITHUB_TOKEN): {msg}")
