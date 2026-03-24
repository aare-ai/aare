"""Base classes for threat detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, runtime_checkable


@dataclass
class InjectionThreat:
    """A detected prompt injection or jailbreak threat.

    Attributes:
        threat_type: Type of threat (e.g., "jailbreak", "prompt_injection",
            "system_prompt_extraction").
        text: The text that triggered detection.
        start: Start character offset in the original text.
        end: End character offset in the original text.
        confidence: Confidence score (0.0-1.0).
        description: Human-readable explanation of the threat.
    """
    threat_type: str
    text: str
    start: int
    end: int
    confidence: float
    description: str


@runtime_checkable
class Detector(Protocol):
    """Protocol for threat detectors.

    Any class implementing this protocol can be used with HIPAAInputGuardrail.
    """

    def detect(self, text: str) -> List[InjectionThreat]:
        """Detect threats in text.

        Args:
            text: Input text to analyze.

        Returns:
            List of detected threats.
        """
        ...
