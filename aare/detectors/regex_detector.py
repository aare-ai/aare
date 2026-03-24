"""Regex-based prompt injection detector.

Lightweight detector using pre-compiled patterns to catch common
prompt injection and jailbreak attacks. No model downloads required.
Suitable for demos, low-latency paths, or as a first-pass filter
before an ML classifier.
"""

from __future__ import annotations

import re
from typing import List

from .base import Detector, InjectionThreat

# --- Pattern definitions ---
# Each tuple: (compiled regex, threat_type, description)
# Patterns are case-insensitive.

_JAILBREAK_PATTERNS = [
    (
        re.compile(r"you\s+are\s+now\s+(DAN|evil|unfiltered|unrestricted)", re.IGNORECASE),
        "jailbreak",
        "DAN/persona jailbreak attempt",
    ),
    (
        re.compile(r"(DAN\s+mode|developer\s+mode)\s*(enabled|activated|on)", re.IGNORECASE),
        "jailbreak",
        "DAN/developer mode activation attempt",
    ),
    (
        re.compile(r"act\s+as\s+if\s+you\s+have\s+no\s+(restrictions|guidelines|rules|limits)", re.IGNORECASE),
        "jailbreak",
        "Restriction removal attempt",
    ),
    (
        re.compile(r"pretend\s+(you\s+are|to\s+be)\s+(an?\s+)?(unrestricted|unfiltered|evil|malicious)", re.IGNORECASE),
        "jailbreak",
        "Persona manipulation attempt",
    ),
    (
        re.compile(r"jailbreak(ed|ing)?|bypass\s+(your\s+)?(safety|content|ethical)\s*(filters?|guidelines?|restrictions?)", re.IGNORECASE),
        "jailbreak",
        "Explicit jailbreak or safety bypass attempt",
    ),
    (
        re.compile(r"from\s+now\s+on\s+you\s+(will|must|should|can)\s+(not\s+)?(follow|obey|ignore)", re.IGNORECASE),
        "jailbreak",
        "Behavioral override attempt",
    ),
]

_PROMPT_INJECTION_PATTERNS = [
    (
        re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier|your)\s+(instructions?|directives?|rules?|guidelines?|prompts?)", re.IGNORECASE),
        "prompt_injection",
        "Instruction override attempt",
    ),
    (
        re.compile(r"disregard\s+(all\s+)?(previous|prior|above|earlier|your)\s+(instructions?|directives?|rules?|guidelines?)", re.IGNORECASE),
        "prompt_injection",
        "Instruction disregard attempt",
    ),
    (
        re.compile(r"forget\s+(all\s+)?(previous|prior|your)\s+(instructions?|context|rules?|training)", re.IGNORECASE),
        "prompt_injection",
        "Context reset attempt",
    ),
    (
        re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
        "prompt_injection",
        "Instruction injection via 'new instructions' prefix",
    ),
    (
        re.compile(r"\[system\]|\[INST\]|<<SYS>>|<\|im_start\|>system", re.IGNORECASE),
        "prompt_injection",
        "Chat template injection attempt",
    ),
    (
        re.compile(r"you\s+(must|will|should)\s+(now\s+)?(only\s+)?(respond|answer|act|behave)\s+(as|like|in)", re.IGNORECASE),
        "prompt_injection",
        "Behavioral directive injection",
    ),
    (
        re.compile(r"override\s+(your\s+)?(system|safety|content)\s*(prompt|instructions?|rules?|policy)", re.IGNORECASE),
        "prompt_injection",
        "System override attempt",
    ),
]

_SYSTEM_PROMPT_EXTRACTION_PATTERNS = [
    (
        re.compile(r"(print|output|show|reveal|display|repeat|echo)\s+(me\s+)?(your\s+|the\s+)?(system\s+prompt|initial\s+instructions?|original\s+prompt|hidden\s+prompt|instructions?\s+verbatim)", re.IGNORECASE),
        "system_prompt_extraction",
        "System prompt extraction attempt",
    ),
    (
        re.compile(r"what\s+(are|were)\s+your\s+(system|initial|original|hidden)\s+(instructions?|prompt|rules?|directives?)", re.IGNORECASE),
        "system_prompt_extraction",
        "System prompt interrogation",
    ),
    (
        re.compile(r"(tell|give)\s+me\s+(your\s+)?(system|initial|hidden)\s+(prompt|instructions?|rules?)", re.IGNORECASE),
        "system_prompt_extraction",
        "Direct system prompt request",
    ),
    (
        re.compile(r"repeat\s+(everything|all|the\s+text)\s+(above|before|from\s+the\s+beginning)", re.IGNORECASE),
        "system_prompt_extraction",
        "Context window extraction attempt",
    ),
]

# Combined list for iteration
_ALL_PATTERNS = (
    _JAILBREAK_PATTERNS
    + _PROMPT_INJECTION_PATTERNS
    + _SYSTEM_PROMPT_EXTRACTION_PATTERNS
)


class RegexDetector:
    """Prompt injection detector using pre-compiled regex patterns.

    Catches common prompt injection, jailbreak, and system prompt
    extraction patterns. Lightweight alternative to ML-based detection
    with zero model download overhead.

    Covers three threat categories:
    - **jailbreak**: DAN mode, persona manipulation, restriction removal
    - **prompt_injection**: Instruction override, context reset, template injection
    - **system_prompt_extraction**: Prompt reveal, context window extraction

    Args:
        confidence: Fixed confidence score for all detections.
            Defaults to 0.90 (regex matches are high-confidence
            but pattern-limited).
    """

    def __init__(self, confidence: float = 0.90):
        self.confidence = confidence

    def detect(self, text: str) -> List[InjectionThreat]:
        """Detect prompt injection threats using regex patterns.

        Args:
            text: Input text to analyze.

        Returns:
            List of detected injection threats. Empty if text is clean.
        """
        if not text or not text.strip():
            return []

        threats: List[InjectionThreat] = []
        seen_types: set[str] = set()

        for pattern, threat_type, description in _ALL_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue

            # Avoid duplicate threat types from overlapping patterns
            type_key = f"{threat_type}:{match.start()}"
            if type_key in seen_types:
                continue
            seen_types.add(type_key)

            threats.append(InjectionThreat(
                threat_type=threat_type,
                text=match.group(0),
                start=match.start(),
                end=match.end(),
                confidence=self.confidence,
                description=description,
            ))

        return threats
