"""redaction.py - deterministic secret redaction for OMEGA cognition.

Implements bounded best-effort regex redaction of secrets to ensure cognitive
traces never store private keys, API tokens, passwords, or credentials.
"""
import re
import hashlib

_SECRET_PATTERNS = [
    # Private keys
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
    # Bearer tokens
    (re.compile(r"(?i)\bbearer\s+[a-zA-Z0-9_\-\.]+"), "[REDACTED_BEARER_TOKEN]"),
    # Typical API keys / access tokens (generic entropy heuristic or common prefixes)
    (re.compile(r"(?i)(?:api_key|apikey|access_token|secret_key|secret|password|pwd|token)[\s:=]+[\"']?([a-zA-Z0-9_\-]{16,})[\"']?"), "[REDACTED_CREDENTIAL]"),
    # AWS-style keys
    (re.compile(r"(?i)AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    # GitHub tokens
    (re.compile(r"(?i)gh[pousr]_[a-zA-Z0-9]{36}"), "[REDACTED_GITHUB_TOKEN]"),
    # Standard DB URI passwords
    (re.compile(r"(?i)(://[^:]+:)([^@]+)(@)"), r"\1[REDACTED_PASSWORD]\3"),
]


def redact_text(text: str) -> str:
    """Redact known secret patterns from text."""
    if not text:
        return text
    
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def hash_evidence_content(content: str) -> str:
    """Hash the normalized redacted evidence."""
    # Ensure it's redacted first
    safe_content = redact_text(content)
    # Normalize for hashing (strip trailing whitespace, standard newlines)
    normalized = "\n".join(line.rstrip() for line in safe_content.splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
