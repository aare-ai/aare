"""LangChain HIPAA Guardrail Demo.

This example shows how to use the Aare HIPAA guardrail with LangChain.

Usage:
    pip install aare langchain-openai
    export OPENAI_API_KEY=your-key
    python examples/langchain_demo.py
"""

from aare import HIPAAGuardrail, HIPAAViolationError, create_guardrail

# ============================================================================
# Example 1: Basic standalone check
# ============================================================================

print("=" * 60)
print("Example 1: Basic standalone check")
print("=" * 60)

guardrail = HIPAAGuardrail()

# Test compliant text
compliant_text = "The patient was diagnosed with hypertension and prescribed medication."
result = guardrail.check(compliant_text)
print(f"\nText: {compliant_text}")
print(f"Blocked: {result.blocked}")
print(f"Passed: {result.passed}")

# Test non-compliant text
phi_text = "Patient John Smith, SSN 123-45-6789, was admitted on 01/15/2024."
result = guardrail.check(phi_text)
print(f"\nText: {phi_text}")
print(f"Blocked: {result.blocked}")
print(f"Violations: {result.violations}")

# ============================================================================
# Example 2: Different violation modes
# ============================================================================

print("\n" + "=" * 60)
print("Example 2: Violation modes")
print("=" * 60)

test_text = "Contact Dr. Jane Doe at jane.doe@hospital.com or 555-123-4567"

# Block mode (default)
print("\n--- Block mode ---")
guardrail_block = HIPAAGuardrail(on_violation="block")
result = guardrail_block.check(test_text)
print(f"Action taken: {result.action_taken}")

# Warn mode
print("\n--- Warn mode ---")
guardrail_warn = HIPAAGuardrail(on_violation="warn")
result = guardrail_warn.check(test_text)
print(f"Action taken: {result.action_taken}")
print(f"Text returned: {result.text[:50]}...")

# Redact mode
print("\n--- Redact mode ---")
guardrail_redact = HIPAAGuardrail(on_violation="redact")
result = guardrail_redact.check(test_text)
print(f"Action taken: {result.action_taken}")
print(f"Redacted text: {result.text}")

# ============================================================================
# Example 3: With LangChain (if langchain is installed)
# ============================================================================

print("\n" + "=" * 60)
print("Example 3: LangChain integration")
print("=" * 60)

try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    # Create a mock LLM for demo (just returns input)
    class MockLLM:
        def invoke(self, input):
            # Simulate LLM response that might contain PHI
            return "Based on the records, John Smith (DOB: 03/15/1980) has been a patient since 2019."

    mock_llm = MockLLM()
    guardrail = HIPAAGuardrail(on_violation="block")

    print("\nSimulating LangChain pipeline with HIPAA guardrail...")
    print("LLM would output: 'Based on the records, John Smith (DOB: 03/15/1980)...'")

    try:
        # In a real chain: chain = prompt | llm | guardrail
        llm_output = mock_llm.invoke("test")
        result = guardrail.invoke(llm_output)
        print(f"Response: {result}")
    except HIPAAViolationError as e:
        print(f"Response BLOCKED by HIPAA guardrail!")
        print(f"Violations: {e.result.violations['categories']}")

except ImportError:
    print("LangChain not installed. Install with: pip install langchain-core")
    print("Skipping LangChain example.")

# ============================================================================
# Example 4: Direct verification API
# ============================================================================

print("\n" + "=" * 60)
print("Example 4: Direct verification API")
print("=" * 60)

from aare import HIPAAVerifier, PHIDetection, ComplianceStatus

verifier = HIPAAVerifier()

# Create detections manually (as if from a custom extractor)
entities = [
    PHIDetection("NAMES", "John Smith", 0, 10, 0.95),
    PHIDetection("SSN", "123-45-6789", 20, 31, 0.99),
]

result = verifier.verify(entities)
print(f"\nVerification status: {result.status.value}")
print(f"Is compliant: {result.is_compliant}")
print(f"\nProof:\n{result.proof}")

# Test compliant case
print("\n--- Compliant document ---")
result = verifier.verify([])  # No PHI detected
print(f"Status: {result.status.value}")
print(f"Proof:\n{result.proof}")

print("\n" + "=" * 60)
print("Demo complete!")
print("=" * 60)
