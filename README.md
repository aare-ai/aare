# aare-core

**Formal verification for LLM compliance - the same approach AWS launched in Bedrock Guardrails (Dec 2024).**

Built this independently. Z3 SMT solver validates AI outputs against regulatory constraints (HIPAA, fair lending, trading) with mathematical proofs, not pattern matching.

[Live Demo](https://aare.ai) | [HIPAA Ontology (76 rules)](https://aare.ai/docs-hipaa.html) | [Why This Matters](https://aare.ai/why-automated-reasoning.html)

---

Core verification engine for aare.ai - Z3 SMT solver for LLM compliance verification.

[![PyPI version](https://badge.fury.io/py/aare-core.svg)](https://pypi.org/project/aare-core/)

## Overview

aare-core provides formal verification (Z3 SMT solver) to validate LLM outputs against structured constraints. The key innovation is the **Formula Compiler** - constraints are defined entirely in JSON, with no code changes needed.

```
JSON Formula → Formula Compiler → Z3 Expression → Formal Verification
```

This is the core library used by all cloud deployments:
- [aare-aws](https://github.com/aare-ai/aare-aws) - AWS Lambda
- [aare-azure](https://github.com/aare-ai/aare-azure) - Azure Functions
- [aare-gcp](https://github.com/aare-ai/aare-gcp) - Google Cloud Functions
- [aare-watsonx](https://github.com/aare-ai/aare-watsonx) - IBM Cloud Code Engine

**Documentation**: [Rule Authoring Guide](docs/RULE_AUTHORING_GUIDE.md) | [Web Docs](https://aare.ai/docs.html)

## Installation

```bash
# Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Core library only
pip install aare-core

# With HTTP server support (quotes required for zsh)
pip install "aare-core[server]"
```

## Quick Start

### Command Line (Easiest)

```bash
# Verify compliant text (outputs JSON with proof certificate) - this passes
aare-verify --input "Loan approved: 3% rate, DTI 35%, credit score 720" --ontology mortgage-compliance-v1

# Verify non-compliant text - this fails with violation details
aare-verify --input "Approved despite DTI of 55%" --ontology mortgage-compliance-v1

# Verify from a file
aare-verify --file response.txt --ontology hipaa-v1

# Pipe from another command
echo "The loan amount is $350,000 with DTI of 35%" | aare-verify --ontology fair-lending-v1

# List all available ontologies (10 bundled + custom)
aare-ontologies

# Compact human-readable output (instead of JSON)
aare-verify --input "..." --ontology mortgage-compliance-v1 --compact
```

### HTTP Server

```bash
# Start local server (requires: pip install "aare-core[server]")
aare-serve

# Or with custom port
aare-serve --port 9000

# Test it
curl -X POST http://localhost:8080/verify \
  -H "Content-Type: application/json" \
  -d '{"llm_output": "DTI is 35%", "ontology": "mortgage-compliance-v1"}'
```

### As a Library

```python
from aare_core import FormulaCompiler, LLMParser, SMTVerifier, OntologyLoader

# Load ontology (verification rules)
loader = OntologyLoader()
ontology = loader.load("example")

# Parse LLM output
parser = LLMParser()
data = parser.parse("The value is 50, option A is selected.", ontology)

# Verify against constraints
verifier = SMTVerifier()
result = verifier.verify(data, ontology)

print(result["verified"])  # True or False
print(result["violations"])  # List of constraint violations
```

### With Docker (Self-hosted Server)

```bash
# Clone the repository
git clone https://github.com/aare-ai/aare-core.git
cd aare-core

# Start with Docker Compose
docker-compose up -d

# Verify it's running
curl http://localhost:8080/health
```

### Run Server Directly

```bash
# Clone and install
git clone https://github.com/aare-ai/aare-core.git
cd aare-core
pip install -e .
pip install flask gunicorn

# Run
python app.py
# or with gunicorn
gunicorn --bind 0.0.0.0:8080 app:app
```

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                      aare.ai Framework                        │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                    /verify endpoint                     │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────────────┐     │  │
│  │  │   LLM    │→ │ Ontology │→ │   Z3 SMT Verifier  │     │  │
│  │  │  Parser  │  │  Loader  │  │  + Formula Compiler│     │  │
│  │  └──────────┘  └──────────┘  └────────────────────┘     │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              ↓                                │
│                    Local Filesystem                           │
│                   (./ontologies/*.json)                       │
└───────────────────────────────────────────────────────────────┘
```

## Formula Compiler

The formula compiler translates JSON constraint definitions into Z3 expressions. This enables:

- **No code changes** to add new constraints
- **Domain-agnostic** - works for any verification domain
- **Formally verified** - mathematically provable correctness

### Supported Operators

| Category | Operators |
|----------|-----------|
| **Logical** | `and`, `or`, `not`, `implies`, `ite` (if-then-else) |
| **Comparison** | `==`, `!=`, `<`, `<=`, `>`, `>=` |
| **Arithmetic** | `+`, `-`, `*`, `/`, `min`, `max` |
| **Constants** | `true`, `false`, numeric values |

### Formula Examples

```json
// Simple comparison: value ≤ 100
{"<=": ["value", 100]}

// Negation: ¬prohibited
{"==": ["prohibited", false]}

// Implication: condition_a → condition_b
{"implies": [
  {"==": ["condition_a", true]},
  {"==": ["condition_b", true]}
]}

// Disjunction: option_a ∨ option_b
{"or": [
  {"==": ["option_a", true]},
  {"==": ["option_b", true]}
]}

// Complex: (dti ≤ 43) ∨ (compensating_factors ≥ 2)
{"or": [
  {"<=": ["dti", 43]},
  {">=": ["compensating_factors", 2]}
]}

// If-then-else: conditional value
{"ite": [{">": ["score", 700]}, "approved", "denied"]}

// Min/max: fee capped at lesser of $500 or 3% of loan
{"<=": ["fee", {"min": [500, {"*": ["loan", 0.03]}]}]}
```

## API Reference

### POST /verify

Verifies LLM output against compliance constraints.

```bash
curl -X POST http://localhost:8080/verify \
  -H "Content-Type: application/json" \
  -d '{
    "llm_output": "The value is 50, option A is selected.",
    "ontology": "example"
  }'
```

**Response:**
```json
{
  "verified": true,
  "violations": [],
  "warnings": ["Variables defaulted (not found in input): ['variable_name']"],
  "parsed_data": {
    "value": 50,
    "option_a": true
  },
  "ontology": {
    "name": "example",
    "version": "1.0.0",
    "constraints_checked": 5
  },
  "proof": {
    "method": "Z3 SMT Solver",
    "version": "4.12.1"
  },
  "verification_id": "uuid",
  "execution_time_ms": 45,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**Note:** The `warnings` field appears when variables couldn't be extracted from the LLM output and were defaulted. This helps auditors understand verification scope.

### GET /ontologies

List available ontologies.

```bash
curl http://localhost:8080/ontologies
```

### GET /ontologies/{name}

Get a specific ontology definition.

```bash
curl http://localhost:8080/ontologies/example
```

### GET /health

Health check endpoint.

```bash
curl http://localhost:8080/health
```

### GET /verifications (requires persistence)

List recent verification records.

```bash
curl http://localhost:8080/verifications?limit=50
```

### GET /verifications/{id} (requires persistence)

Retrieve a specific verification record by ID.

```bash
curl http://localhost:8080/verifications/abc-123-uuid
```

## Bundled Ontologies

aare-core ships with 10 production-ready ontologies covering common compliance domains:

| Ontology | Domain | Constraints | Use Case |
|----------|--------|-------------|----------|
| `mortgage-compliance-v1` | Lending | 5 | ATR/QM, HOEPA, UDAAP compliance |
| `hipaa-v1` | Healthcare | 52 | HIPAA Privacy & Security Rule |
| `medical-safety-v1` | Healthcare | 5 | Drug interactions, dosing limits |
| `financial-compliance-v1` | Finance | 5 | Investment advice, disclaimers |
| `fair-lending-v1` | Lending | 5 | DTI limits, credit score requirements |
| `data-privacy-v1` | Security | 5 | PII detection, credential exposure |
| `customer-service-v1` | Support | 5 | Discount limits, delivery promises |
| `trading-compliance-v1` | Trading | 5 | Position limits, sector exposure |
| `content-policy-v1` | Content | 5 | Real people, medical advice |
| `contract-compliance-v1` | Legal | 5 | Usury limits, late fee caps |

Use any ontology by name:

```bash
aare-verify --input "Your response" --ontology hipaa-v1
```

## Creating Custom Ontologies

Create your own verification rules by adding JSON files to the `ontologies/` directory.

> **Full Documentation**: See the comprehensive [Rule Authoring Guide](docs/RULE_AUTHORING_GUIDE.md) for detailed instructions, examples, and best practices. Also available at [aare.ai/docs](https://aare.ai/docs.html).

### Ontology Structure

```json
{
  "name": "my-custom-ontology",
  "version": "1.0.0",
  "description": "Description of your ontology",
  "constraints": [
    {
      "id": "UNIQUE_CONSTRAINT_ID",
      "category": "Category Name",
      "description": "What this constraint checks",
      "formula_readable": "human-readable formula",
      "formula": {"<=": ["value", 100]},
      "variables": [
        {"name": "value", "type": "real"}
      ],
      "error_message": "Error shown when violated",
      "citation": "Reference to regulation/policy"
    }
  ],
  "extractors": {
    "value": {
      "type": "float",
      "pattern": "value[:\\s]*(\\d+(?:\\.\\d+)?)"
    }
  }
}
```

### Variable Types

| Type | Z3 Type | Use For |
|------|---------|---------|
| `bool` | `Bool` | True/false flags |
| `int` | `Int` | Whole numbers |
| `real` or `float` | `Real` | Decimal numbers |

### Extractor Types

| Type | Description | Example |
|------|-------------|---------|
| `boolean` | True if any keyword found | `{"keywords": ["approved", "accepted"]}` |
| `int` | Extract integer from regex | `{"pattern": "score[:\\s]*(\\d+)"}` |
| `float` | Extract decimal number | `{"pattern": "(\\d+\\.\\d+)%"}` |
| `money` | Extract currency (handles k/m/b) | `{"pattern": "\\$([\\d,]+)k?"}` |
| `percentage` | Extract percentage | `{"pattern": "(\\d+(?:\\.\\d+)?)%"}` |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | HTTP port |
| `ONTOLOGY_DIR` | `./ontologies` | Directory for custom ontologies |
| `CORS_ORIGINS` | `https://aare.ai,...` | Comma-separated allowed origins |
| `DEBUG` | `false` | Enable debug mode |
| `AARE_PERSISTENCE` | *(none)* | Enable audit trail persistence (see below) |

### Persistence (Audit Trail)

Enable optional persistence to store verification records for audit trails, compliance reporting, and historical analysis.

```bash
# SQLite (recommended for single-node deployments)
AARE_PERSISTENCE=sqlite://verifications.db aare-serve

# In-memory (testing only - data lost on restart)
AARE_PERSISTENCE=memory aare-serve
```

When persistence is enabled:
- Each verification is stored with a `certificate_hash` (SHA256 of verification metadata)
- The original LLM output is hashed (not stored) for integrity verification
- New endpoints become available: `GET /verifications` and `GET /verifications/{id}`
- The `/health` endpoint includes `"persistence": true`

**Programmatic usage:**

```python
from aare_core import SQLiteStore, InMemoryStore
from aare_core.server import create_app

# Use SQLite
store = SQLiteStore("verifications.db")
app = create_app(store=store)

# Or create a custom backend
from aare_core import VerificationStore, VerificationRecord

class PostgresStore(VerificationStore):
    def store(self, record: VerificationRecord) -> str:
        # Store record, return certificate_hash
        ...

    def retrieve(self, verification_id: str) -> VerificationRecord | None:
        # Retrieve by ID
        ...

app = create_app(store=PostgresStore(connection_string))
```

### Docker Compose Configuration

```yaml
version: '3.8'

services:
  aare:
    image: ghcr.io/aare-ai/aare:latest
    ports:
      - "8080:8080"
    environment:
      - CORS_ORIGINS=https://your-domain.com
      - AARE_PERSISTENCE=sqlite:///data/verifications.db
    volumes:
      - ./ontologies:/app/ontologies:ro
      - ./data:/data
    restart: unless-stopped
```

## Production Deployment

### With Nginx (SSL)

```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### With Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aare-ai
spec:
  replicas: 3
  selector:
    matchLabels:
      app: aare-ai
  template:
    metadata:
      labels:
        app: aare-ai
    spec:
      containers:
      - name: aare-ai
        image: ghcr.io/aare-ai/aare:latest
        ports:
        - containerPort: 8080
        env:
        - name: CORS_ORIGINS
          value: "https://your-domain.com"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "2"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
```

## Integration Example

```python
import requests

def verify_llm_output(llm_response: str, ontology: str = "example") -> dict:
    """Verify LLM output before returning to user"""
    result = requests.post(
        "http://localhost:8080/verify",
        json={
            "llm_output": llm_response,
            "ontology": ontology
        }
    ).json()

    if not result["verified"]:
        raise ComplianceError(
            f"Verification failed: {result['violations']}"
        )

    return result

# Usage
llm_output = my_llm.generate(prompt)
verification = verify_llm_output(llm_output)
if verification["verified"]:
    return llm_output
```

## Performance

aare-core is optimized for high-throughput verification. Benchmarks on a standard laptop:

| Test | Throughput | p99 Latency |
|------|-----------|-------------|
| Single-threaded | ~320 req/s | 4 ms |
| Multi-process (4 workers) | ~1,600 req/s | 3 ms |
| Complex ontology (50+ constraints) | ~40 req/s | 30 ms |

Run the stress test yourself:

```bash
python tests/stress_test.py --requests 5000 --workers 4
```

The multi-process mode achieves near-linear scaling. Z3 is not thread-safe, so we use separate processes for concurrent workloads.

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- Documentation: https://aare.ai/about
- Issues: https://github.com/aare-ai/aare-core/issues
- Contact: info@aare.ai
