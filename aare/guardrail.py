"""HIPAA Guardrail for LangChain.

Drop-in guardrail that verifies LLM outputs are HIPAA compliant
before they reach end users.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Literal, Optional, Union

from langchain_core.runnables import Runnable, RunnableConfig

from .extractors.base import PHIEntity, Extractor
from .verification.hipaa import (
    ComplianceStatus,
    HIPAAVerifier,
    PHIDetection,
    VerificationResult,
)

logger = logging.getLogger(__name__)


class HIPAAViolationError(Exception):
    """Raised when HIPAA violation is detected and on_violation='block'."""

    def __init__(self, result: VerificationResult):
        self.result = result
        super().__init__(f"HIPAA violation detected: {result.violations}")


class GuardrailResult:
    """Result of guardrail check."""

    def __init__(
        self,
        text: str,
        verification: VerificationResult,
        action_taken: str
    ):
        self.text = text
        self.original_text = text
        self.verification = verification
        self.action_taken = action_taken

    @property
    def blocked(self) -> bool:
        """Whether the text was blocked."""
        return self.action_taken == "blocked"

    @property
    def passed(self) -> bool:
        """Whether the text passed verification."""
        return self.verification.is_compliant

    @property
    def violations(self):
        """Get violation details."""
        return self.verification.violations

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "blocked": self.blocked,
            "passed": self.passed,
            "action_taken": self.action_taken,
            "verification": self.verification.to_dict()
        }


class HIPAAGuardrail(Runnable):
    """HIPAA compliance guardrail for LangChain.

    Intercepts LLM outputs and verifies they don't contain
    prohibited PHI before delivering to users.

    Example:
        ```python
        from aare import HIPAAGuardrail
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI()
        guardrail = HIPAAGuardrail()

        # As a chain component
        chain = prompt | llm | guardrail

        # Or standalone
        result = guardrail.check("Patient John Smith, SSN 123-45-6789")
        if result.blocked:
            print(f"Blocked: {result.violations}")
        ```

    Args:
        extractor: PHI extractor to use. Defaults to RegexExtractor.
        on_violation: Action on violation:
            - "block": Raise HIPAAViolationError (default)
            - "warn": Log warning, return original text
            - "redact": Replace PHI with [REDACTED], return sanitized text
    """

    def __init__(
        self,
        extractor: Optional[Extractor] = None,
        on_violation: Literal["block", "warn", "redact"] = "block"
    ):
        self.on_violation = on_violation
        self._verifier = HIPAAVerifier()

        # Default to regex extractor (no dependencies)
        if extractor is None:
            from .extractors.regex import RegexExtractor
            self._extractor = RegexExtractor()
        else:
            self._extractor = extractor

    def _convert_entities(self, entities: List[PHIEntity]) -> List[PHIDetection]:
        """Convert PHIEntity to PHIDetection for verifier."""
        return [
            PHIDetection(
                category=e.entity_type,
                value=e.text,
                start=e.start,
                end=e.end,
                confidence=e.confidence
            )
            for e in entities
        ]

    def check(self, text: str) -> GuardrailResult:
        """Check text for HIPAA compliance.

        Args:
            text: Text to verify.

        Returns:
            GuardrailResult with verification details.
        """
        # Extract entities
        entities = self._extractor.extract(text)
        detections = self._convert_entities(entities)

        # Verify
        result = self._verifier.verify(detections)

        if result.is_compliant:
            return GuardrailResult(
                text=text,
                verification=result,
                action_taken="passed"
            )

        # Handle violation
        if self.on_violation == "block":
            return GuardrailResult(
                text=text,
                verification=result,
                action_taken="blocked"
            )
        elif self.on_violation == "warn":
            logger.warning(f"HIPAA violation detected: {result.violations}")
            return GuardrailResult(
                text=text,
                verification=result,
                action_taken="warned"
            )
        elif self.on_violation == "redact":
            redacted = self._redact_phi(text, entities)
            return GuardrailResult(
                text=redacted,
                verification=result,
                action_taken="redacted"
            )

        return GuardrailResult(
            text=text,
            verification=result,
            action_taken="unknown"
        )

    def _redact_phi(self, text: str, entities: List[PHIEntity]) -> str:
        """Replace PHI with [REDACTED] markers."""
        # Sort by position (reverse) to avoid offset issues
        sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)

        result = text
        for entity in sorted_entities:
            result = (
                result[:entity.start] +
                f"[REDACTED:{entity.entity_type}]" +
                result[entity.end:]
            )

        return result

    def invoke(
        self,
        input: Any,
        config: Optional[RunnableConfig] = None
    ) -> str:
        """Process input through the guardrail.

        This is the LangChain Runnable interface.

        Args:
            input: Text to verify (string or object with content attribute).
            config: LangChain config (unused).

        Returns:
            Original or redacted text (depending on on_violation).

        Raises:
            HIPAAViolationError: If violation detected and on_violation='block'.
        """
        # Handle various input types
        if hasattr(input, "content"):
            text = input.content
        elif isinstance(input, str):
            text = input
        else:
            text = str(input)

        result = self.check(text)

        if result.blocked:
            raise HIPAAViolationError(result.verification)

        return result.text

    async def ainvoke(
        self,
        input: Any,
        config: Optional[RunnableConfig] = None
    ) -> str:
        """Async version of invoke."""
        return self.invoke(input, config)

    @property
    def InputType(self):
        """Input type for the runnable."""
        return str

    @property
    def OutputType(self):
        """Output type for the runnable."""
        return str


def create_guardrail(
    extractor: str = "regex",
    on_violation: Literal["block", "warn", "redact"] = "block",
    **kwargs
) -> HIPAAGuardrail:
    """Factory function to create a guardrail with specified extractor.

    Args:
        extractor: Extractor type - "regex" or "presidio".
        on_violation: Action on violation.
        **kwargs: Additional arguments for the extractor.

    Returns:
        Configured HIPAAGuardrail.
    """
    if extractor == "presidio":
        from .extractors.presidio import PresidioExtractor
        ext = PresidioExtractor(**kwargs)
    else:
        from .extractors.regex import RegexExtractor
        ext = RegexExtractor(**kwargs)

    return HIPAAGuardrail(extractor=ext, on_violation=on_violation)
