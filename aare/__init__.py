"""Aare - HIPAA Guardrails for AI Agents.

Formal verification for LLM outputs using Z3 theorem proving.

Example:
    ```python
    from aare import HIPAAGuardrail

    guardrail = HIPAAGuardrail()

    # Check text directly
    result = guardrail.check("Patient John Smith, SSN 123-45-6789")
    if result.blocked:
        print(f"Blocked: {result.violations}")

    # Or use with LangChain
    from langchain_openai import ChatOpenAI
    chain = prompt | ChatOpenAI() | guardrail
    ```
"""

__version__ = "0.1.0"

from .guardrail import (
    HIPAAGuardrail,
    HIPAAViolationError,
    GuardrailResult,
    create_guardrail,
)
from .verification import (
    HIPAAVerifier,
    HIPAARules,
    PHIDetection,
    VerificationResult,
    ComplianceStatus,
)
from .extractors.base import PHIEntity, Extractor

__all__ = [
    # Main API
    "HIPAAGuardrail",
    "HIPAAViolationError",
    "GuardrailResult",
    "create_guardrail",
    # Verification
    "HIPAAVerifier",
    "HIPAARules",
    "PHIDetection",
    "VerificationResult",
    "ComplianceStatus",
    # Extractors
    "PHIEntity",
    "Extractor",
]
