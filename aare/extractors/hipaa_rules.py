"""HIPAA Rules-based PHI extractor.

Extends DistilBERT extraction with explicit rule-based detection for
HIPAA Safe Harbor requirements that the neural model may miss:

1. Ages over 89 (must be aggregated to 90+)
2. Employee IDs, badge numbers, and other unique identifiers
3. Temporal inference risks (specific times + locations)
4. First names in sensitive contexts (psychotherapy, etc.)

Also includes negative rules to reduce false positives on clinical values.

CFR References:
- 45 CFR 164.514(b)(2)(i)(C) - Ages over 89
- 45 CFR 164.514(b)(2)(i)(R) - Other unique identifying numbers
- 45 CFR 164.508(a)(2) - Psychotherapy notes
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple, Set

from .base import Extractor, PHIEntity


# Patterns that should trigger PHI detection
HIPAA_RULES: List[Tuple[str, str, str]] = [
    # Ages over 89 - HIPAA requires aggregation to "90+"
    # CFR: 45 CFR 164.514(b)(2)(i)(C)
    (
        r"\b(9[0-9]|1[0-9]{2}|[2-9][0-9]{2,})[\s-]*(year|yr)s?[\s-]*old\b",
        "DATES",
        "Age over 89 must be aggregated to 90+ per Safe Harbor"
    ),
    (
        r"\bage[:\s]*(9[0-9]|1[0-9]{2})\b",
        "DATES",
        "Age over 89 must be aggregated to 90+ per Safe Harbor"
    ),

    # Employee IDs, Badge Numbers, Staff IDs
    # CFR: 45 CFR 164.514(b)(2)(i)(R)
    (
        r"\b(employee|emp|badge|staff|worker|personnel)[\s]*(id|#|number|no\.?)[\s:]*[A-Z0-9][\w-]{3,}\b",
        "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER",
        "Employee/staff identifier"
    ),
    (
        r"\bbadge[\s]*(number|#|no\.?)[\s:]*[A-Z0-9][\w-]{3,}\b",
        "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER",
        "Badge number identifier"
    ),

    # Customer/Client/Member codes (when in health context)
    (
        r"\b(customer|client|patient)[\s]*(code|id|#|number)[\s:]*[A-Z0-9][\w-]{3,}\b",
        "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER",
        "Customer/client identifier"
    ),

    # Case numbers, file numbers
    (
        r"\b(case|file|record)[\s]*(#|number|no\.?)[\s:]*[A-Z0-9][\w-]{4,}\b",
        "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER",
        "Case/file number identifier"
    ),

    # Specific times in clinical context (temporal inference risk)
    # Times like "3:47 AM" combined with room numbers enable identification
    (
        r"\b([01]?[0-9]|2[0-3]):([0-5][0-9])\s*(AM|PM|am|pm)\b",
        "DATES",
        "Specific time may enable temporal identification"
    ),

    # Room numbers in clinical context
    (
        r"\b(room|rm|bed)[\s#]*(\d{3,4}[A-Z]?)\b",
        "GEOGRAPHIC_SUBDIVISIONS",
        "Room/bed number in clinical context"
    ),

    # Relative dates that could be resolved (yesterday, last Tuesday, etc.)
    (
        r"\b(yesterday|last\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
        "DATES",
        "Relative date can be resolved to specific date"
    ),

    # Psychotherapy/therapy session context with first names
    # CFR: 45 CFR 164.508(a)(2)
    # Look for first names after "session" context words
    (
        r"\b(therapy|counseling|psychiatric|psychotherapy)\s+session[,\s]+([A-Z][a-z]{2,15})\s+(discussed|talked|shared|expressed|reported|said)",
        "NAMES",
        "Name in psychotherapy context requires separate authorization"
    ),
]

# Patterns that should NOT trigger detection (false positive suppressors)
# These are matched and used to filter OUT entities from the neural model
FALSE_POSITIVE_PATTERNS: List[Tuple[str, Set[str]]] = [
    # Lab values with common labels (WBC, Hemoglobin, etc.)
    (
        r"\b(WBC|RBC|Hgb|Hct|MCV|MCH|MCHC|RDW|Plt|Platelets|BUN|Cr|Creatinine|Na|K|Cl|CO2|Glucose|Ca|Mg|Phos|AST|ALT|ALP|GGT|Bili|Bilirubin|Albumin|Protein|A1c|HbA1c|TSH|T4|T3|INR|PT|PTT|aPTT|Troponin|BNP|proBNP|Lactate|Ammonia|Lipase|Amylase|CRP|ESR|Ferritin|Iron|TIBC|B12|Folate|Vitamin|eGFR|GFR|Hemoglobin|Hematocrit|WBC|Neutrophils|Lymphocytes|Monocytes|Eosinophils|Basophils)[:\s]*\d{1,4}(\.\d{1,2})?\b",
        {"IP_ADDRESSES", "PHONE_NUMBERS", "VEHICLE_IDENTIFIERS"}
    ),

    # Lab values that look like IP addresses (e.g., "7.2", "14.1")
    # Format: value (unit) or value (normal: range)
    (
        r"\b\d{1,3}\.\d{1,2}\s*\([^)]*\)",
        {"IP_ADDRESSES", "PHONE_NUMBERS"}
    ),

    # Lab reference ranges (e.g., "4.5-11.0", "70-100", "normal: 4.5-11.0")
    (
        r"\b(normal|ref|reference)?[:\s]*\d{1,3}(\.\d{1,2})?[-–]\d{1,3}(\.\d{1,2})?\b",
        {"IP_ADDRESSES", "PHONE_NUMBERS", "VEHICLE_IDENTIFIERS"}
    ),

    # Vital signs patterns (BP, HR, SpO2, etc.)
    (
        r"\b(BP|HR|RR|SpO2|O2\s*sat|temp)\s*[:=]?\s*\d{2,3}[/\d]*",
        {"IP_ADDRESSES", "PHONE_NUMBERS", "VEHICLE_IDENTIFIERS"}
    ),

    # Blood pressure pattern (e.g., "145/92")
    (
        r"\b\d{2,3}/\d{2,3}\b",
        {"IP_ADDRESSES", "VEHICLE_IDENTIFIERS"}
    ),

    # Percentages (e.g., "98%", "45.5%")
    (
        r"\b\d{1,3}(\.\d{1,2})?\s*%",
        {"IP_ADDRESSES", "VEHICLE_IDENTIFIERS"}
    ),

    # Common lab units that might confuse the model
    (
        r"\b\d{1,3}(\.\d{1,2})?\s*(mg|mL|mcg|mmol|mEq|units?|IU|ng|pg|g/dL|mmHg)\b",
        {"IP_ADDRESSES", "VEHICLE_IDENTIFIERS"}
    ),

    # Truncated ZIP codes (permitted under Safe Harbor)
    # Pattern: 021**, 123xx, etc.
    (
        r"\b\d{3}[\*xX]{2}\b",
        {"GEOGRAPHIC_SUBDIVISIONS"}
    ),

    # Generic medication dosages
    (
        r"\b\d{1,4}\s*(mg|mcg|mL|units?)\s+(daily|BID|TID|QID|PRN|QHS|QAM|QPM)\b",
        {"VEHICLE_IDENTIFIERS", "IP_ADDRESSES"}
    ),

    # Clinical score patterns (PHQ-9, GAD-7, etc.)
    (
        r"\b(PHQ|GAD|MMSE|GCS|APGAR|BMI)[-\s]*\d{1,2}\b",
        {"VEHICLE_IDENTIFIERS", "IP_ADDRESSES"}
    ),
]


class HIPAARulesExtractor(Extractor):
    """HIPAA-specific extractor with rule-based gap closure.

    This extractor wraps another extractor (typically DistilBERT) and adds:
    1. Explicit rules for HIPAA requirements the model may miss
    2. False positive suppression for clinical values

    Args:
        base_extractor: The underlying extractor to wrap (e.g., DistilBERTExtractor).
            If None, only rule-based detection is used.
        enable_age_detection: Detect ages over 89 (default: True)
        enable_unique_id_detection: Detect employee IDs, badge numbers (default: True)
        enable_temporal_detection: Detect specific times in clinical context (default: True)
        enable_false_positive_suppression: Filter out clinical false positives (default: True)
    """

    def __init__(
        self,
        base_extractor: Optional[Extractor] = None,
        enable_age_detection: bool = True,
        enable_unique_id_detection: bool = True,
        enable_temporal_detection: bool = True,
        enable_false_positive_suppression: bool = True,
    ):
        self.base_extractor = base_extractor
        self.enable_age_detection = enable_age_detection
        self.enable_unique_id_detection = enable_unique_id_detection
        self.enable_temporal_detection = enable_temporal_detection
        self.enable_false_positive_suppression = enable_false_positive_suppression

        # Compile rule patterns
        self._rules = []
        for pattern, entity_type, description in HIPAA_RULES:
            # Filter rules based on settings
            if not enable_age_detection and "Age over 89" in description:
                continue
            if not enable_unique_id_detection and entity_type == "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER":
                continue
            if not enable_temporal_detection and "temporal" in description.lower():
                continue

            self._rules.append((
                re.compile(pattern, re.IGNORECASE),
                entity_type,
                description
            ))

        # Compile false positive patterns
        self._fp_suppressors = []
        if enable_false_positive_suppression:
            for pattern, suppressed_types in FALSE_POSITIVE_PATTERNS:
                self._fp_suppressors.append((
                    re.compile(pattern, re.IGNORECASE),
                    suppressed_types
                ))

    def extract(self, text: str) -> List[PHIEntity]:
        """Extract PHI entities using base extractor + HIPAA rules.

        Args:
            text: Input text to analyze.

        Returns:
            List of detected PHI entities with HIPAA category labels.
        """
        if not text or not text.strip():
            return []

        # Get base extractor results
        entities = []
        if self.base_extractor:
            entities = list(self.base_extractor.extract(text))

        # Apply false positive suppression
        if self.enable_false_positive_suppression:
            entities = self._suppress_false_positives(text, entities)

        # Apply HIPAA rules
        rule_entities = self._apply_rules(text)

        # Merge entities, avoiding duplicates
        all_entities = self._merge_entities(entities, rule_entities)

        # Sort by position
        all_entities.sort(key=lambda e: e.start)

        return all_entities

    def _apply_rules(self, text: str) -> List[PHIEntity]:
        """Apply rule-based detection patterns."""
        entities = []
        seen_spans = set()

        for pattern, entity_type, description in self._rules:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())

                # Skip if we've already detected something at this location
                if span in seen_spans:
                    continue

                # Check for overlapping spans
                overlaps = False
                for seen_start, seen_end in seen_spans:
                    if match.start() < seen_end and match.end() > seen_start:
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
                    confidence=0.95,  # Rule-based matches are high confidence
                ))

        return entities

    def _suppress_false_positives(
        self, text: str, entities: List[PHIEntity]
    ) -> List[PHIEntity]:
        """Filter out entities that match false positive patterns."""
        if not entities:
            return entities

        # Find all false positive regions
        fp_regions = []
        for pattern, suppressed_types in self._fp_suppressors:
            for match in pattern.finditer(text):
                fp_regions.append((match.start(), match.end(), suppressed_types))

        # Filter entities
        filtered = []
        for entity in entities:
            should_suppress = False

            for fp_start, fp_end, suppressed_types in fp_regions:
                # Check if entity overlaps with false positive region
                if entity.start < fp_end and entity.end > fp_start:
                    # Check if entity type should be suppressed
                    if entity.entity_type in suppressed_types:
                        should_suppress = True
                        break

            if not should_suppress:
                filtered.append(entity)

        return filtered

    def _merge_entities(
        self, base_entities: List[PHIEntity], rule_entities: List[PHIEntity]
    ) -> List[PHIEntity]:
        """Merge entities from base extractor and rules, avoiding duplicates."""
        all_entities = list(base_entities)
        seen_spans = {(e.start, e.end) for e in base_entities}

        for entity in rule_entities:
            span = (entity.start, entity.end)

            # Skip exact duplicates
            if span in seen_spans:
                continue

            # Check for overlapping spans (prefer base extractor)
            overlaps = False
            for existing in base_entities:
                if entity.start < existing.end and entity.end > existing.start:
                    overlaps = True
                    break

            if not overlaps:
                all_entities.append(entity)
                seen_spans.add(span)

        return all_entities
