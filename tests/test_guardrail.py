"""Tests for HIPAA guardrail."""

import pytest
from aare import (
    HIPAAGuardrail,
    HIPAAViolationError,
    GuardrailResult,
    create_guardrail,
)


class TestHIPAAGuardrail:
    """Tests for HIPAAGuardrail class."""

    def test_compliant_text_passes(self):
        """Compliant text should pass verification."""
        guardrail = HIPAAGuardrail()
        result = guardrail.check("The patient was diagnosed with hypertension.")

        assert result.passed
        assert not result.blocked
        assert result.action_taken == "passed"

    def test_phi_text_blocked(self):
        """Text with PHI should be blocked."""
        guardrail = HIPAAGuardrail(on_violation="block")
        result = guardrail.check("Patient SSN is 123-45-6789")

        assert result.blocked
        assert not result.passed
        assert result.action_taken == "blocked"
        assert result.violations is not None

    def test_phi_detection_ssn(self):
        """SSN should be detected as PHI."""
        guardrail = HIPAAGuardrail()
        result = guardrail.check("SSN: 123-45-6789")

        assert result.blocked
        assert "SSN" in str(result.violations)

    def test_phi_detection_phone(self):
        """Phone number should be detected as PHI."""
        guardrail = HIPAAGuardrail()
        result = guardrail.check("Call me at 555-123-4567")

        assert result.blocked

    def test_phi_detection_email(self):
        """Email should be detected as PHI."""
        guardrail = HIPAAGuardrail()
        result = guardrail.check("Email: patient@hospital.com")

        assert result.blocked

    def test_warn_mode_returns_text(self):
        """Warn mode should return original text."""
        guardrail = HIPAAGuardrail(on_violation="warn")
        text = "Patient SSN: 123-45-6789"
        result = guardrail.check(text)

        assert result.action_taken == "warned"
        assert result.text == text

    def test_redact_mode_removes_phi(self):
        """Redact mode should replace PHI with markers."""
        guardrail = HIPAAGuardrail(on_violation="redact")
        result = guardrail.check("SSN: 123-45-6789")

        assert result.action_taken == "redacted"
        assert "[REDACTED:" in result.text
        assert "123-45-6789" not in result.text

    def test_invoke_raises_on_violation(self):
        """Invoke should raise HIPAAViolationError when blocking."""
        guardrail = HIPAAGuardrail(on_violation="block")

        with pytest.raises(HIPAAViolationError) as exc_info:
            guardrail.invoke("Patient SSN: 123-45-6789")

        assert exc_info.value.result.violations is not None

    def test_invoke_returns_text_when_compliant(self):
        """Invoke should return text when compliant."""
        guardrail = HIPAAGuardrail()
        text = "The diagnosis was hypertension."

        result = guardrail.invoke(text)
        assert result == text

    def test_create_guardrail_factory(self):
        """Factory function should create guardrails."""
        guardrail = create_guardrail(extractor="regex", on_violation="warn")

        assert isinstance(guardrail, HIPAAGuardrail)
        assert guardrail.on_violation == "warn"


class TestGuardrailResult:
    """Tests for GuardrailResult class."""

    def test_to_dict(self):
        """Result should convert to dictionary."""
        guardrail = HIPAAGuardrail()
        result = guardrail.check("Test text")

        d = result.to_dict()
        assert "text" in d
        assert "blocked" in d
        assert "passed" in d
        assert "verification" in d
