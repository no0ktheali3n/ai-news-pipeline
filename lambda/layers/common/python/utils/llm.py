# utils/llm.py — provider-agnostic LLM completion layer.
#
# Primary: AWS Bedrock (anthropic messages API).
# Fallback: OpenRouter (OpenAI chat-completions API).
#
# All envs are read at CALL time (not import) so tests can flip them freely.
# Module import must never raise (Lambda-safe).

import json
import logging
import os
import re

import boto3
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model-id mapping table (Bedrock → OpenRouter slug)
# ---------------------------------------------------------------------------

_MODEL_TABLE = {
    # Haiku 4.5 — various prefixes
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "anthropic/claude-haiku-4.5",
    "anthropic.claude-haiku-4-5-20251001-v1:0": "anthropic/claude-haiku-4.5",
    "global.anthropic.claude-haiku-4-5-20251001-v1:0": "anthropic/claude-haiku-4.5",
    # Sonnet 4.6
    "us.anthropic.claude-sonnet-4-6-20260101-v1:0": "anthropic/claude-sonnet-4.6",
    "anthropic.claude-sonnet-4-6-20260101-v1:0": "anthropic/claude-sonnet-4.6",
    "global.anthropic.claude-sonnet-4-6-20260101-v1:0": "anthropic/claude-sonnet-4.6",
    # Sonnet 4.5 (dated id)
    "us.anthropic.claude-sonnet-4-5-20251001-v1:0": "anthropic/claude-sonnet-4.5",
    "anthropic.claude-sonnet-4-5-20251001-v1:0": "anthropic/claude-sonnet-4.5",
    "global.anthropic.claude-sonnet-4-5-20251001-v1:0": "anthropic/claude-sonnet-4.5",
}

# Regex for generic Bedrock ids: (us|global).anthropic.claude-<name>-<maj>-<min>...
_BEDROCK_RE = re.compile(
    r"^(?:us|global)\.anthropic\.claude-([a-z]+)-(\d)-(\d)"
)


class LLMError(Exception):
    """Raised when an LLM provider call fails."""

    def __init__(self, provider: str, *args):
        super().__init__(*args)
        self.provider = provider


# ---------------------------------------------------------------------------
# Lazy Bedrock client — created on first use, reused across calls.
# Module import must NEVER raise (Lambda-safe; plan invariant), and
# boto3.client() at import time can raise on credential/config issues.
# ---------------------------------------------------------------------------

_bedrock = None


def _get_bedrock():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client(
            "bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
    return _bedrock


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def to_openrouter_model(model_id: str) -> str:
    """Translate a Bedrock model id to its OpenRouter slug.

    Resolution order:
    1. LLM_MODEL_MAP env (JSON dict) override — checked FIRST.
    2. Explicit table (_MODEL_TABLE).
    3. Regex derivation for (us|global).anthropic.claude-<name>-<maj>-<min>.
    4. Pass-through if model_id already contains '/'.
    5. Raise LLMError for anything else.
    """
    # 1. Optional override map from env
    model_map_raw = os.getenv("LLM_MODEL_MAP", "")
    if model_map_raw:
        try:
            model_map = json.loads(model_map_raw)
            if model_id in model_map:
                return model_map[model_id]
        except (json.JSONDecodeError, TypeError):
            logger.warning("LLM_MODEL_MAP is not valid JSON; ignoring")

    # 2. Explicit table
    if model_id in _MODEL_TABLE:
        return _MODEL_TABLE[model_id]

    # 3. Regex derivation
    m = _BEDROCK_RE.match(model_id)
    if m:
        name, maj, minor = m.group(1), m.group(2), m.group(3)
        return f"anthropic/claude-{name}-{maj}.{minor}"

    # 4. Pass-through for already-slugged ids
    if "/" in model_id:
        return model_id

    raise LLMError("mapping", f"Cannot map model id to OpenRouter slug: {model_id!r}")


# ---------------------------------------------------------------------------
# Provider adapters
# ---------------------------------------------------------------------------


def _call_bedrock(prompt: str, model: str, max_tokens: int, temperature: float) -> str:
    """Invoke Bedrock using the anthropic messages payload shape."""
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = _get_bedrock().invoke_model(
        modelId=model,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(payload),
    )
    result = json.loads(response["body"].read())
    text = " ".join(
        p["text"] for p in result.get("content", []) if p.get("type") == "text"
    )
    return text


def _call_openrouter(prompt: str, model: str, max_tokens: int, temperature: float) -> str:
    """Call OpenRouter chat-completions endpoint."""
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise LLMError("openrouter", "OPENROUTER_API_KEY is not set")

    or_model = to_openrouter_model(model)
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": or_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise LLMError(
            "openrouter",
            f"OpenRouter returned HTTP {resp.status_code}: {resp.text[:200]}",
        )
    data = resp.json()
    choices = data.get("choices")
    if not choices:
        raise LLMError("openrouter", f"OpenRouter response missing choices: {data!r}")
    content = choices[0].get("message", {}).get("content")
    if content is None:
        raise LLMError("openrouter", f"OpenRouter choice missing message.content: {choices[0]!r}")
    return content


# ---------------------------------------------------------------------------
# Provider dispatch map (extend here for future providers)
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "bedrock": _call_bedrock,
    "openrouter": _call_openrouter,
}


def _provider_usable(provider: str) -> bool:
    """Return True if the named provider can be called without a config error."""
    if provider == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY", ""))
    # bedrock is always structurally usable (may still fail at runtime)
    return provider in _PROVIDERS


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def complete(
    prompt: str,
    *,
    model: str,
    max_tokens: int,
    temperature: float = 0.2,
) -> str:
    """Call the configured LLM provider and return the completion text.

    Falls back to LLM_FALLBACK_PROVIDER if the primary raises any Exception.
    Raises LLMError on complete failure.
    """
    primary = os.getenv("LLM_PROVIDER", "bedrock")
    fallback = os.getenv("LLM_FALLBACK_PROVIDER", "")

    primary_fn = _PROVIDERS.get(primary)
    if primary_fn is None:
        raise LLMError(primary, f"Unknown LLM provider: {primary!r}")

    try:
        return primary_fn(prompt, model, max_tokens, temperature)
    except Exception as primary_exc:
        # No fallback configured → wrap and raise
        if not fallback or fallback == primary:
            raise LLMError(primary, str(primary_exc)) from primary_exc

        # Fallback configured — check usability first
        if not _provider_usable(fallback):
            logger.warning(
                "LLM fallback provider %r is configured but not usable "
                "(missing key?); treating as no fallback. Primary error: %s",
                fallback,
                primary_exc,
            )
            raise LLMError(primary, str(primary_exc)) from primary_exc

        fallback_fn = _PROVIDERS.get(fallback)
        if fallback_fn is None:
            raise LLMError(primary, f"Unknown fallback provider: {fallback!r}") from primary_exc

        logger.warning(
            "LLM primary provider %r failed (%s); retrying with fallback %r",
            primary,
            primary_exc,
            fallback,
        )
        try:
            return fallback_fn(prompt, model, max_tokens, temperature)
        except Exception as fallback_exc:
            raise LLMError(fallback, str(fallback_exc)) from fallback_exc
