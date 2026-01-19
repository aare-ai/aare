"""HIPAA Compliance Verification using Z3 Theorem Proving.

Provides formal verification of HIPAA Safe Harbor de-identification
based on 45 CFR 164.514(b)(2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from z3 import Bool, Not, Or, Solver, unsat


@dataclass
class PHIDetection:
    """A detected PHI entity."""
    category: str
    value: str
    start: int
    end: int
    confidence: float = 1.0


class ComplianceStatus(Enum):
    """HIPAA compliance status."""
    COMPLIANT = "compliant"
    VIOLATION = "violation"
    ERROR = "error"


@dataclass
class VerificationResult:
    """Result of HIPAA verification."""
    status: ComplianceStatus
    entities: List[PHIDetection]
    proof: str
    violations: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_compliant(self) -> bool:
        """Check if verification passed."""
        return self.status == ComplianceStatus.COMPLIANT

    @property
    def is_violation(self) -> bool:
        """Check if verification found violations."""
        return self.status == ComplianceStatus.VIOLATION

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "entities": [
                {
                    "category": e.category,
                    "value": e.value,
                    "start": e.start,
                    "end": e.end,
                    "confidence": e.confidence
                }
                for e in self.entities
            ],
            "proof": self.proof,
            "violations": self.violations,
            "metadata": self.metadata
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class HIPAARules:
    """HIPAA Safe Harbor de-identification rules.

    Based on 45 CFR 164.514(b)(2) - the 18 categories of PHI
    that must be removed for Safe Harbor de-identification.
    """

    # The 18 HIPAA Safe Harbor categories
    PROHIBITED_CATEGORIES = [
        "NAMES",
        "GEOGRAPHIC_SUBDIVISIONS",
        "DATES",
        "PHONE_NUMBERS",
        "FAX_NUMBERS",
        "EMAIL_ADDRESSES",
        "SSN",
        "MEDICAL_RECORD_NUMBERS",
        "HEALTH_PLAN_BENEFICIARY_NUMBERS",
        "ACCOUNT_NUMBERS",
        "CERTIFICATE_LICENSE_NUMBERS",
        "VEHICLE_IDENTIFIERS",
        "DEVICE_IDENTIFIERS",
        "WEB_URLS",
        "IP_ADDRESSES",
        "BIOMETRIC_IDENTIFIERS",
        "PHOTOGRAPHIC_IMAGES",
        "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER",
    ]

    # Mapping from common extractor labels to HIPAA categories
    LABEL_MAP = {
        # Names
        "PERSON": "NAMES",
        "NAME": "NAMES",
        "PATIENT": "NAMES",
        "DOCTOR": "NAMES",
        "PER": "NAMES",
        # Geographic
        "LOCATION": "GEOGRAPHIC_SUBDIVISIONS",
        "LOC": "GEOGRAPHIC_SUBDIVISIONS",
        "GPE": "GEOGRAPHIC_SUBDIVISIONS",
        "ADDRESS": "GEOGRAPHIC_SUBDIVISIONS",
        "CITY": "GEOGRAPHIC_SUBDIVISIONS",
        "ZIP": "GEOGRAPHIC_SUBDIVISIONS",
        "STATE": "GEOGRAPHIC_SUBDIVISIONS",
        # Dates
        "DATE": "DATES",
        "DATE_TIME": "DATES",
        "AGE": "DATES",
        "DOB": "DATES",
        # Contact
        "PHONE": "PHONE_NUMBERS",
        "PHONE_NUMBER": "PHONE_NUMBERS",
        "FAX": "FAX_NUMBERS",
        "EMAIL": "EMAIL_ADDRESSES",
        "EMAIL_ADDRESS": "EMAIL_ADDRESSES",
        # IDs
        "SSN": "SSN",
        "US_SSN": "SSN",
        "SOCIAL_SECURITY_NUMBER": "SSN",
        "MEDICAL_RECORD": "MEDICAL_RECORD_NUMBERS",
        "MRN": "MEDICAL_RECORD_NUMBERS",
        "HEALTH_PLAN": "HEALTH_PLAN_BENEFICIARY_NUMBERS",
        "ACCOUNT": "ACCOUNT_NUMBERS",
        "ACCOUNT_NUMBER": "ACCOUNT_NUMBERS",
        "LICENSE": "CERTIFICATE_LICENSE_NUMBERS",
        "LICENSE_PLATE": "VEHICLE_IDENTIFIERS",
        "VEHICLE": "VEHICLE_IDENTIFIERS",
        "VIN": "VEHICLE_IDENTIFIERS",
        "DEVICE": "DEVICE_IDENTIFIERS",
        "DEVICE_ID": "DEVICE_IDENTIFIERS",
        "URL": "WEB_URLS",
        "IP_ADDRESS": "IP_ADDRESSES",
        "IP": "IP_ADDRESSES",
        "BIOMETRIC": "BIOMETRIC_IDENTIFIERS",
        "PHOTO": "PHOTOGRAPHIC_IMAGES",
        # Generic
        "ID": "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER",
        "IDENTIFIER": "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER",
        "OTHER": "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER",
    }

    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """Initialize HIPAA rules.

        Args:
            config_path: Optional path to custom config (not typically needed).
        """
        self._config_path = config_path

    def get_prohibited_categories(self) -> List[str]:
        """Get list of all prohibited HIPAA categories."""
        return self.PROHIBITED_CATEGORIES.copy()

    def is_prohibited(self, category: str) -> bool:
        """Check if a category is prohibited PHI."""
        # Check direct match
        if category.upper() in self.PROHIBITED_CATEGORIES:
            return True
        # Check mapped category
        mapped = self.LABEL_MAP.get(category.upper())
        if mapped and mapped in self.PROHIBITED_CATEGORIES:
            return True
        return False

    def normalize_category(self, category: str) -> str:
        """Normalize a category label to HIPAA standard."""
        upper = category.upper()
        if upper in self.PROHIBITED_CATEGORIES:
            return upper
        return self.LABEL_MAP.get(upper, upper)

    def create_z3_constraints(
        self,
        detections: List[PHIDetection],
        solver: Solver
    ) -> Dict[str, Bool]:
        """Create Z3 constraints for detected PHI.

        Args:
            detections: List of detected PHI entities.
            solver: Z3 Solver instance.

        Returns:
            Dictionary mapping category names to Z3 Bool variables.
        """
        category_vars = {}
        for category in self.PROHIBITED_CATEGORIES:
            category_vars[category] = Bool(f"{category}_detected")

        # Set variables based on detections
        detected_categories = {
            self.normalize_category(d.category)
            for d in detections
        }

        for category, var in category_vars.items():
            if category in detected_categories:
                solver.add(var == True)
            else:
                solver.add(var == False)

        return category_vars


class HIPAAVerifier:
    """HIPAA compliance verifier using Z3 theorem proving.

    Provides formal verification that text contains no prohibited
    PHI as defined by HIPAA Safe Harbor.
    """

    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """Initialize verifier.

        Args:
            config_path: Optional path to custom HIPAA config.
        """
        self.rules = HIPAARules(config_path)

    def verify(self, entities: List[PHIDetection]) -> VerificationResult:
        """Verify HIPAA compliance for detected entities.

        Args:
            entities: List of PHI entities detected by an extractor.

        Returns:
            VerificationResult with compliance status and proof.
        """
        solver = Solver()

        # Create constraints
        category_vars = self.rules.create_z3_constraints(entities, solver)

        # Get prohibited category variables
        prohibited_vars = [
            category_vars[cat]
            for cat in self.rules.get_prohibited_categories()
            if cat in category_vars
        ]

        # Check: can we satisfy "no prohibited PHI"?
        solver.push()
        if prohibited_vars:
            solver.add(Not(Or(prohibited_vars)))

        result = solver.check()
        solver.pop()

        if result == unsat:
            # UNSAT = prohibited PHI was detected = VIOLATION
            violations = self._create_violations(entities)
            proof = self._create_violation_proof(violations)

            return VerificationResult(
                status=ComplianceStatus.VIOLATION,
                entities=entities,
                proof=proof,
                violations=violations,
                metadata={"solver_result": "unsat"}
            )
        else:
            # SAT = no prohibited PHI = COMPLIANT
            proof = self._create_compliant_proof(entities)

            return VerificationResult(
                status=ComplianceStatus.COMPLIANT,
                entities=entities,
                proof=proof,
                violations=None,
                metadata={"solver_result": "sat"}
            )

    def verify_text(
        self,
        text: str,
        extractor: Optional[Callable[[str], List[PHIDetection]]] = None
    ) -> VerificationResult:
        """Verify HIPAA compliance for text.

        Args:
            text: Text to verify.
            extractor: Function that extracts PHI from text.

        Returns:
            VerificationResult.
        """
        if extractor is None:
            return VerificationResult(
                status=ComplianceStatus.ERROR,
                entities=[],
                proof="No extractor provided.",
                metadata={"error": "no_extractor"}
            )

        try:
            entities = extractor(text)
            return self.verify(entities)
        except Exception as e:
            return VerificationResult(
                status=ComplianceStatus.ERROR,
                entities=[],
                proof=f"Extraction error: {e}",
                metadata={"error": str(e)}
            )

    def _create_violations(
        self,
        entities: List[PHIDetection]
    ) -> Dict[str, Any]:
        """Create violation details."""
        violations = []
        for entity in entities:
            normalized = self.rules.normalize_category(entity.category)
            if self.rules.is_prohibited(normalized):
                violations.append({
                    "category": normalized,
                    "original_label": entity.category,
                    "value": entity.value,
                    "location": {"start": entity.start, "end": entity.end},
                    "confidence": entity.confidence,
                })

        return {
            "count": len(violations),
            "violations": violations,
            "categories": list(set(v["category"] for v in violations))
        }

    def _create_violation_proof(self, violations: Dict[str, Any]) -> str:
        """Create human-readable violation proof."""
        lines = [
            "HIPAA VIOLATION DETECTED",
            "=" * 40,
            f"Found {violations['count']} prohibited PHI element(s)",
            "",
        ]

        for v in violations["violations"]:
            lines.append(f"Category: {v['category']}")
            lines.append(f"  Value: {v['value']}")
            lines.append(f"  Position: {v['location']['start']}-{v['location']['end']}")
            lines.append(f"  Confidence: {v['confidence']:.2f}")
            lines.append("")

        lines.append(f"Violated categories: {', '.join(violations['categories'])}")
        return "\n".join(lines)

    def _create_compliant_proof(self, entities: List[PHIDetection]) -> str:
        """Create human-readable compliance proof."""
        lines = [
            "HIPAA COMPLIANT",
            "=" * 40,
            "No prohibited PHI identifiers detected.",
            "",
            "Verified against all 18 HIPAA Safe Harbor categories.",
        ]
        return "\n".join(lines)
