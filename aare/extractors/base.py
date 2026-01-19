"""Base classes for PHI extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, runtime_checkable


@dataclass
class PHIEntity:
    """A detected PHI entity.

    Attributes:
        entity_type: The type of entity (e.g., "PERSON", "SSN", "DATE").
        text: The actual text that was detected.
        start: Start character offset in the original text.
        end: End character offset in the original text.
        confidence: Confidence score (0.0-1.0).
    """
    entity_type: str
    text: str
    start: int
    end: int
    confidence: float = 1.0


@runtime_checkable
class Extractor(Protocol):
    """Protocol for PHI extractors.

    Any class implementing this protocol can be used with HIPAAGuardrail.
    """

    def extract(self, text: str) -> List[PHIEntity]:
        """Extract PHI entities from text.

        Args:
            text: Input text to analyze.

        Returns:
            List of detected PHI entities.
        """
        ...
