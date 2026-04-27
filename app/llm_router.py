import os
import time
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def _call_openrouter(prompt: str, model: str, max_retries: int = 3) -> Optional[str]:
    """Call OpenRouter API with exponential backoff."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set, skipping OpenRouter")
        return None

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                timeout=30,
            )
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning(f"OpenRouter rate limit, retrying in {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f"OpenRouter attempt {attempt + 1} failed: {e}, retrying in {wait}s")
            time.sleep(wait)

    return None


def _call_openai(prompt: str, model: str, max_retries: int = 3) -> Optional[str]:
    """Call OpenAI API with exponential backoff."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set, skipping OpenAI")
        return None

    try:
        import openai
    except ImportError:
        logger.error("openai package not installed")
        return None

    client = openai.OpenAI(api_key=api_key)
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=30,
            )
            return resp.choices[0].message.content
        except openai.RateLimitError:
            wait = 2 ** attempt
            logger.warning(f"OpenAI rate limit, retrying in {wait}s")
            time.sleep(wait)
        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f"OpenAI attempt {attempt + 1} failed: {e}, retrying in {wait}s")
            time.sleep(wait)

    return None


def call_llm(prompt: str, settings: dict) -> Optional[str]:
    """Route LLM call: primary (OpenRouter) → fallback (OpenAI)."""
    ai_cfg = settings.get("ai", {})
    primary = ai_cfg.get("primary", "openrouter")
    fallback = ai_cfg.get("fallback", "openai")

    if primary == "openrouter":
        result = _call_openrouter(prompt, ai_cfg.get("openrouter_model", "google/gemma-3-27b-it:free"))
        if result:
            return result
        logger.info("OpenRouter failed, falling back to OpenAI")

    if fallback == "openai" or primary == "openai":
        result = _call_openai(prompt, ai_cfg.get("openai_model", "gpt-4o-mini"))
        if result:
            return result

    logger.error("Both OpenRouter and OpenAI failed")
    return None
