"""Presidio-based PHI extractor.

Uses Microsoft Presidio for PHI detection. Requires:
    pip install presidio-analyzer

For better accuracy, also install spaCy model:
    python -m spacy download en_core_web_lg
"""

from __future__ import annotations

from typing import List, Optional

from .base import PHIEntity, Extractor


class PresidioExtractor(Extractor):
    """PHI extractor using Microsoft Presidio.

    Presidio provides production-grade PII/PHI detection with
    support for multiple entity types and languages.
    """

    # Presidio entity types to extract (HIPAA-relevant)
    DEFAULT_ENTITIES = [
        "PERSON",
        "LOCATION",
        "DATE_TIME",
        "PHONE_NUMBER",
        "EMAIL_ADDRESS",
        "US_SSN",
        "MEDICAL_LICENSE",
        "URL",
        "IP_ADDRESS",
        "CREDIT_CARD",
        "US_BANK_NUMBER",
        "US_DRIVER_LICENSE",
        "US_PASSPORT",
    ]

    def __init__(
        self,
        entities: Optional[List[str]] = None,
        language: str = "en",
        score_threshold: float = 0.5
    ):
        """Initialize Presidio extractor.

        Args:
            entities: Entity types to detect. Defaults to HIPAA-relevant types.
            language: Language code. Defaults to "en".
            score_threshold: Minimum confidence score. Defaults to 0.5.
        """
        try:
            from presidio_analyzer import AnalyzerEngine
        except ImportError:
            raise ImportError(
                "Presidio is not installed. Install with: pip install aare[presidio]"
            )

        self.entities = entities or self.DEFAULT_ENTITIES
        self.language = language
        self.score_threshold = score_threshold
        self._analyzer = AnalyzerEngine()

    def extract(self, text: str) -> List[PHIEntity]:
        """Extract PHI entities using Presidio.

        Args:
            text: Input text to analyze.

        Returns:
            List of detected PHI entities.
        """
        results = self._analyzer.analyze(
            text=text,
            entities=self.entities,
            language=self.language,
            score_threshold=self.score_threshold
        )

        entities = []
        for result in results:
            entities.append(PHIEntity(
                entity_type=result.entity_type,
                text=text[result.start:result.end],
                start=result.start,
                end=result.end,
                confidence=result.score
            ))

        return entities
