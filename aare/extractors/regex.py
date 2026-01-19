"""Regex-based PHI extractor.

A simple, dependency-free extractor for common PHI patterns.
Useful for testing and basic use cases. For production, use Presidio.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .base import PHIEntity, Extractor


class RegexExtractor(Extractor):
    """Simple regex-based PHI extractor.

    Detects common PHI patterns without external dependencies.
    For production use, consider PresidioExtractor instead.
    """

    # Patterns for common PHI types
    PATTERNS: List[Tuple[str, str]] = [
        # SSN: XXX-XX-XXXX or XXXXXXXXX
        (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
        (r"\b\d{9}\b", "SSN"),

        # Phone: various formats
        (r"\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "PHONE_NUMBER"),
        (r"\b\+1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "PHONE_NUMBER"),

        # Email
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "EMAIL_ADDRESS"),

        # IP Address (IPv4)
        (r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b", "IP_ADDRESS"),

        # URLs
        (r"\bhttps?://[^\s<>\"{}|\\^`\[\]]+\b", "URL"),

        # Dates: MM/DD/YYYY, MM-DD-YYYY, YYYY-MM-DD
        (r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "DATE"),
        (r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", "DATE"),

        # Medical Record Number patterns
        (r"\bMRN[:\s#]*\d{6,10}\b", "MEDICAL_RECORD"),
        (r"\bMedical Record[:\s#]*\d{6,10}\b", "MEDICAL_RECORD"),

        # ZIP codes (5 or 9 digit)
        (r"\b\d{5}(?:-\d{4})?\b", "ZIP"),

        # Credit card (basic pattern)
        (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", "CREDIT_CARD"),
    ]

    def __init__(self, additional_patterns: List[Tuple[str, str]] = None):
        """Initialize regex extractor.

        Args:
            additional_patterns: Extra (pattern, entity_type) tuples to use.
        """
        self.patterns = self.PATTERNS.copy()
        if additional_patterns:
            self.patterns.extend(additional_patterns)

        # Compile patterns
        self._compiled = [
            (re.compile(pattern, re.IGNORECASE), entity_type)
            for pattern, entity_type in self.patterns
        ]

    def extract(self, text: str) -> List[PHIEntity]:
        """Extract PHI entities using regex patterns.

        Args:
            text: Input text to analyze.

        Returns:
            List of detected PHI entities.
        """
        entities = []
        seen_spans = set()  # Avoid duplicates

        for pattern, entity_type in self._compiled:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())

                # Skip if we've already detected something at this location
                if span in seen_spans:
                    continue

                # Check for overlapping spans
                overlaps = False
                for seen_start, seen_end in seen_spans:
                    if (match.start() < seen_end and match.end() > seen_start):
                        overlaps = True
                        break

                if overlaps:
                    continue

                seen_spans.add(span)
                entities.append(PHIEntity(
                    entity_type=entity_type,
                    text=match.group(),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.9  # Regex matches are high confidence
                ))

        # Sort by position
        entities.sort(key=lambda e: e.start)
        return entities
