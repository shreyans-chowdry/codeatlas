"""
Embedding generation using Voyage AI (voyage-code-3).
"""
import os
import time
import random
import logging
from typing import Union, List, Dict, Any
import voyageai

logger = logging.getLogger(__name__)

VOYAGE_MODEL = "voyage-code-3"
BATCH_SIZE = 100
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0


def _embed_batch_with_retry(client: voyageai.Client, batch: List[str]) -> List[List[float]]:
    """
    Embeds a single batch of texts with exponential backoff on 429 rate limits
    and transient server errors.
    """
    retries = 0
    backoff = INITIAL_BACKOFF
    while True:
        try:
            result = client.embed(
                texts=batch,
                model=VOYAGE_MODEL,
                input_type="document"
            )
            return result.embeddings
        except Exception as e:
            error_msg = str(e).lower()
            is_rate_limit = "429" in error_msg or "rate limit" in error_msg or "ratelimit" in error_msg
            is_transient = "500" in error_msg or "503" in error_msg or "server error" in error_msg or "timeout" in error_msg

            if (is_rate_limit or is_transient) and retries < MAX_RETRIES:
                retries += 1
                jitter = random.uniform(0, 0.5)
                sleep_duration = backoff + jitter
                logger.warning(
                    f"Voyage AI rate limit / transient error encountered: {e}. Retrying {retries}/{MAX_RETRIES} in {sleep_duration:.2f}s..."
                )
                time.sleep(sleep_duration)
                backoff *= 2
            else:
                logger.error(f"Failed to embed batch with Voyage AI: {e}")
                raise


def embed_chunks(chunks: List[Union[Dict[str, Any], str]]) -> List[List[float]]:
    """
    Calls the Voyage AI API using the voyage-code-3 model with input_type="document".
    Batches requests (up to 100 chunks per API call) and includes retry-with-backoff
    on rate-limit (429) responses.
    
    Accepts either a list of chunk dicts (containing a 'content' key) or a list of raw strings.
    """
    if not chunks:
        return []

    texts = [c["content"] if isinstance(c, dict) else str(c) for c in chunks]
    client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        batch_embeddings = _embed_batch_with_retry(client, batch)
        all_embeddings.extend(batch_embeddings)

    return all_embeddings
