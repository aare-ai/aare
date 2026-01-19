"""Tests for HIPAA verification engine."""

import pytest
from aare.verification.hipaa import (
    HIPAAVerifier,
    HIPAARules,
    PHIDetection,
    VerificationResult,
    ComplianceStatus,
)


class TestHIPAARules:
    """Tests for HIPAARules class."""

    def test_prohibited_categories(self):
        """Should have 18 prohibited categories."""
        rules = HIPAARules()
        categories = rules.get_prohibited_categories()

        assert len(categories) == 18
        assert "NAMES" in categories
        assert "SSN" in categories
        assert "EMAIL_ADDRESSES" in categories

    def test_is_prohibited(self):
        """Should correctly identify prohibited categories."""
        rules = HIPAARules()

        assert rules.is_prohibited("NAMES")
        assert rules.is_prohibited("SSN")
        assert not rules.is_prohibited("UNKNOWN_CATEGORY")

    def test_normalize_category(self):
        """Should normalize category labels."""
        rules = HIPAARules()

        assert rules.normalize_category("PERSON") == "NAMES"
        assert rules.normalize_category("US_SSN") == "SSN"
        assert rules.normalize_category("LOCATION") == "GEOGRAPHIC_SUBDIVISIONS"

    def test_label_mapping(self):
        """Common extractor labels should map to HIPAA categories."""
        rules = HIPAARules()

        # Test various mappings
        assert rules.is_prohibited("PERSON")  # Maps to NAMES
        assert rules.is_prohibited("EMAIL")  # Maps to EMAIL_ADDRESSES
        assert rules.is_prohibited("PHONE")  # Maps to PHONE_NUMBERS


class TestHIPAAVerifier:
    """Tests for HIPAAVerifier class."""

    def test_empty_entities_compliant(self):
        """No entities should be compliant."""
        verifier = HIPAAVerifier()
        result = verifier.verify([])

        assert result.status == ComplianceStatus.COMPLIANT
        assert result.is_compliant
        assert not result.is_violation

    def test_phi_entity_violation(self):
        """PHI entity should cause violation."""
        verifier = HIPAAVerifier()
        entities = [
            PHIDetection("NAMES", "John Smith", 0, 10, 0.95)
        ]

        result = verifier.verify(entities)

        assert result.status == ComplianceStatus.VIOLATION
        assert result.is_violation
        assert result.violations is not None
        assert result.violations["count"] == 1

    def test_multiple_phi_entities(self):
        """Multiple PHI entities should all be reported."""
        verifier = HIPAAVerifier()
        entities = [
            PHIDetection("NAMES", "John Smith", 0, 10, 0.95),
            PHIDetection("SSN", "123-45-6789", 20, 31, 0.99),
        ]

        result = verifier.verify(entities)

        assert result.status == ComplianceStatus.VIOLATION
        assert result.violations["count"] == 2
        assert "NAMES" in result.violations["categories"]
        assert "SSN" in result.violations["categories"]

    def test_proof_contains_details(self):
        """Proof should contain violation details."""
        verifier = HIPAAVerifier()
        entities = [
            PHIDetection("SSN", "123-45-6789", 0, 11, 0.99)
        ]

        result = verifier.verify(entities)

        assert "VIOLATION" in result.proof
        assert "SSN" in result.proof

    def test_compliant_proof(self):
        """Compliant result should have appropriate proof."""
        verifier = HIPAAVerifier()
        result = verifier.verify([])

        assert "COMPLIANT" in result.proof
        assert "18 HIPAA" in result.proof


class TestVerificationResult:
    """Tests for VerificationResult class."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        result = VerificationResult(
            status=ComplianceStatus.COMPLIANT,
            entities=[],
            proof="Test proof"
        )

        d = result.to_dict()
        assert d["status"] == "compliant"
        assert d["proof"] == "Test proof"
        assert d["entities"] == []

    def test_to_json(self):
        """Should convert to JSON string."""
        result = VerificationResult(
            status=ComplianceStatus.COMPLIANT,
            entities=[],
            proof="Test"
        )

        json_str = result.to_json()
        assert '"status": "compliant"' in json_str

    def test_is_compliant_property(self):
        """is_compliant property should work correctly."""
        compliant = VerificationResult(
            status=ComplianceStatus.COMPLIANT,
            entities=[],
            proof=""
        )
        violation = VerificationResult(
            status=ComplianceStatus.VIOLATION,
            entities=[],
            proof=""
        )

        assert compliant.is_compliant
        assert not compliant.is_violation
        assert not violation.is_compliant
        assert violation.is_violation
