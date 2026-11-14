"""Bounded, opt-in Claude API calls for the agent modules.

Model calls are OFF unless AGENTS_MODEL_ENABLED=1. Even then they need the
`anthropic` package (a runtime dependency request recorded for Codex in
docs/CLAUDE_STATUS.md) and credentials that the SDK can resolve
(ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile).

Any failure raises ProviderError; callers fall back to the deterministic path
and label their output accordingly. Secrets are never read, logged, or put in
error messages by this module; the SDK resolves credentials itself.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_TIMEOUT_SECONDS = 8.0
MAX_RETRIES = 1  # SDK-level retry for 408/409/429/5xx/connection errors
MAX_TOKENS = 2048


class ProviderError(Exception):
    """Model call unavailable or failed. Message is safe to surface as a warning."""


def model_enabled() -> bool:
    return os.environ.get("AGENTS_MODEL_ENABLED") == "1"


def _timeout() -> float:
    try:
        value = float(os.environ.get("AGENTS_MODEL_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return min(max(value, 1.0), 30.0)


def complete_text(system: str, user: str) -> str:
    """Send one bounded request and return the concatenated text output.

    Raises ProviderError when disabled, when the SDK is missing, on timeout,
    API errors, refusals, truncation, or empty output.
    """
    if not model_enabled():
        raise ProviderError("Model calls are disabled (AGENTS_MODEL_ENABLED is not 1).")
    try:
        import anthropic  # imported lazily so ordinary startup never needs it
    except ImportError as exc:
        raise ProviderError("The anthropic package is not installed.") from exc

    model = os.environ.get("AGENTS_MODEL", DEFAULT_MODEL)
    try:
        client = anthropic.Anthropic(timeout=_timeout(), max_retries=MAX_RETRIES)
        # Server-side refusal fallback ("default" routing) is enabled so a
        # classifier decline is retried on a suitable model inside the same call.
        response = client.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APITimeoutError as exc:
        raise ProviderError("Model call timed out.") from exc
    except anthropic.AuthenticationError as exc:
        raise ProviderError("Model credentials were rejected or missing.") from exc
    except anthropic.RateLimitError as exc:
        raise ProviderError("Model call was rate limited.") from exc
    except anthropic.APIStatusError as exc:
        raise ProviderError(f"Model API returned HTTP {exc.status_code}.") from exc
    except anthropic.APIConnectionError as exc:
        raise ProviderError("Could not reach the model API.") from exc
    except Exception as exc:  # e.g. no resolvable credentials raises at client creation
        raise ProviderError(f"Model call failed ({type(exc).__name__}).") from exc

    if response.stop_reason == "refusal":
        raise ProviderError("Model declined the request.")
    if response.stop_reason == "max_tokens":
        raise ProviderError("Model output was truncated.")
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    if not text.strip():
        raise ProviderError("Model returned no text.")
    return text
