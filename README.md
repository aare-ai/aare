# aare-core

HIPAA guardrails for AI agents. Formal verification for LLM outputs using Z3 theorem proving.

[![PyPI version](https://badge.fury.io/py/aare-core.svg)](https://pypi.org/project/aare-core/)

## Why Aare?

AI agents are being deployed in healthcare, but current guardrails are inadequate:

- **Prompt engineering**: "Please don't violate HIPAA" - not enforceable
- **Regex filters**: Brittle, easy to bypass, can't understand context
- **Human review**: Doesn't scale, defeats the purpose of automation

Aare provides **mathematically proven** HIPAA compliance verification using Z3 theorem proving. Not regex hope.

## Installation

```bash
pip install aare-core
```

For better PHI detection, install with Presidio:

```bash
pip install aare-core[presidio]
```

## Quick Start

### Standalone Check

```python
from aare import HIPAAGuardrail

guardrail = HIPAAGuardrail()

# Check text for HIPAA compliance
result = guardrail.check("Patient John Smith, SSN 123-45-6789, was admitted on 01/15/2024")

if result.blocked:
    print(f"HIPAA violation detected!")
    print(f"Violations: {result.violations}")
else:
    print("Text is HIPAA compliant")
```

### With LangChain

```python
from aare import HIPAAGuardrail
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOpenAI()
guardrail = HIPAAGuardrail()

prompt = ChatPromptTemplate.from_template("Summarize: {text}")

# Guardrail blocks responses containing PHI
chain = prompt | llm | guardrail

try:
    response = chain.invoke({"text": "..."})
    print(response)  # Safe response
except HIPAAViolationError as e:
    print(f"Response blocked: {e.result.violations}")
```

## Configuration

### Violation Handling

```python
# Block (default) - raises HIPAAViolationError
guardrail = HIPAAGuardrail(on_violation="block")

# Warn - logs warning, returns original text
guardrail = HIPAAGuardrail(on_violation="warn")

# Redact - replaces PHI with [REDACTED:TYPE], returns sanitized text
guardrail = HIPAAGuardrail(on_violation="redact")
```

### PHI Extractors

```python
# Default: regex-based (no dependencies)
guardrail = HIPAAGuardrail()

# Presidio: better accuracy (requires: pip install aare[presidio])
from aare.extractors.presidio import PresidioExtractor
guardrail = HIPAAGuardrail(extractor=PresidioExtractor())

# Or use the factory function
from aare import create_guardrail
guardrail = create_guardrail(extractor="presidio")
```

## What Gets Detected

Aare detects all 18 HIPAA Safe Harbor categories:

| Category | Examples |
|----------|----------|
| Names | John Smith, Dr. Jane Doe |
| Geographic | 123 Main St, Boston, 02115 |
| Dates | 01/15/1985, DOB, admission dates |
| Phone numbers | (555) 123-4567 |
| Fax numbers | Fax: 555-123-4568 |
| Email addresses | patient@email.com |
| SSN | 123-45-6789 |
| Medical record numbers | MRN: 12345678 |
| Health plan numbers | Member ID: XYZ123 |
| Account numbers | Account #12345 |
| License numbers | License: DL123456 |
| Vehicle identifiers | VIN, license plates |
| Device identifiers | Pacemaker S/N |
| URLs | http://patient-portal.example.com |
| IP addresses | 192.168.1.100 |
| Biometric identifiers | Fingerprint ID |
| Photos | Full-face images |
| Other identifiers | Employee ID, badge numbers |

## How It Works

```
LLM Response
    ↓
PHI Extractor (Regex or Presidio)
    ↓
List of detected entities
    ↓
Z3 Theorem Prover
    ↓
PASS (compliant) or BLOCK (violation with proof)
```

The Z3 theorem prover provides **formal verification** - not pattern matching, but mathematical proof that the text either contains or doesn't contain prohibited PHI.

## API Reference

### HIPAAGuardrail

```python
HIPAAGuardrail(
    extractor: Extractor = None,  # PHI extraction method
    on_violation: str = "block"   # "block", "warn", or "redact"
)
```

**Methods:**

- `check(text: str) -> GuardrailResult` - Check text, return result
- `invoke(input) -> str` - LangChain Runnable interface

### GuardrailResult

```python
result.blocked     # bool - Was the text blocked?
result.passed      # bool - Did verification pass?
result.violations  # dict - Violation details (if any)
result.text        # str - Original or redacted text
```

### HIPAAViolationError

Raised when `on_violation="block"` and PHI is detected.

```python
try:
    response = guardrail.invoke(llm_output)
except HIPAAViolationError as e:
    print(e.result.violations)
```

## Examples

### Redacting PHI

```python
guardrail = HIPAAGuardrail(on_violation="redact")

result = guardrail.check("Call John Smith at 555-123-4567")
print(result.text)
# "Call [REDACTED:PERSON] at [REDACTED:PHONE_NUMBER]"
```

### Custom Extractor

```python
from aare import HIPAAGuardrail, PHIEntity, Extractor

class MyExtractor(Extractor):
    def extract(self, text: str) -> list[PHIEntity]:
        # Your extraction logic
        return [
            PHIEntity(
                entity_type="SSN",
                text="123-45-6789",
                start=10,
                end=21,
                confidence=0.99
            )
        ]

guardrail = HIPAAGuardrail(extractor=MyExtractor())
```

### Direct Verification

```python
from aare import HIPAAVerifier, PHIDetection

verifier = HIPAAVerifier()

# Verify pre-extracted entities
entities = [
    PHIDetection("NAMES", "John Smith", 0, 10, 0.95),
    PHIDetection("SSN", "123-45-6789", 15, 26, 0.99),
]

result = verifier.verify(entities)
print(result.status)  # ComplianceStatus.VIOLATION
print(result.proof)   # Human-readable explanation
```

## Development

```bash
# Clone
git clone https://github.com/aare-ai/aare-core.git
cd aare-core

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Links

- **Website**: https://aare.ai
- **Documentation**: https://aare.ai/docs
- **Issues**: https://github.com/aare-ai/aare-core/issues
- **Contact**: info@aare.ai
