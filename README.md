# aare.ai - Self-Hosted Verification Engine

Self-hosted deployment of the aare.ai Z3 SMT verification engine. Run your own instance with Docker or directly on any server.

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/aare-ai/aare.git
cd aare

# Start with Docker Compose
docker-compose up -d

# Verify it's running
curl http://localhost:8080/health
```

### Option 2: Docker Run

```bash
docker run -d \
  --name aare-ai \
  -p 8080:8080 \
  -v $(pwd)/ontologies:/app/ontologies:ro \
  ghcr.io/aare-ai/aare:latest
```

### Option 3: Run Directly

```bash
# Clone and install
git clone https://github.com/aare-ai/aare.git
cd aare
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run
python app.py
# or with gunicorn
gunicorn --bind 0.0.0.0:8080 app:app
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     aare.ai (Self-Hosted)                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    /verify endpoint                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────────────┐     │   │
│  │  │   LLM    │→ │ Ontology │→ │   Z3 SMT Verifier  │     │   │
│  │  │  Parser  │  │  Loader  │  │  (Constraint Logic)│     │   │
│  │  └──────────┘  └──────────┘  └────────────────────┘     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│                    Local Filesystem                             │
│                   (./ontologies/*.json)                         │
└─────────────────────────────────────────────────────────────────┘
```

## API Reference

### POST /verify

Verifies LLM output against compliance constraints.

```bash
curl -X POST http://localhost:8080/verify \
  -H "Content-Type: application/json" \
  -d '{
    "llm_output": "Based on your DTI of 35% and FICO score of 720, you are approved for a $350,000 mortgage.",
    "ontology": "mortgage-compliance-v1"
  }'
```

**Response:**
```json
{
  "verified": true,
  "violations": [],
  "parsed_data": {
    "dti": 35,
    "credit_score": 720,
    "loan_amount": 350000
  },
  "ontology": {
    "name": "mortgage-compliance-v1",
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

### GET /ontologies

List available ontologies.

```bash
curl http://localhost:8080/ontologies
```

### GET /ontologies/{name}

Get a specific ontology definition.

```bash
curl http://localhost:8080/ontologies/mortgage-compliance-v1
```

### GET /health

Health check endpoint.

```bash
curl http://localhost:8080/health
```

## Built-in Ontologies

| Ontology | Description |
|----------|-------------|
| `mortgage-compliance-v1` | U.S. mortgage lending compliance (ATR/QM, HOEPA, UDAAP, Reg B) |
| `fair-lending-v1` | Fair lending regulations |
| `hipaa-v1` | HIPAA PHI protection |

## Custom Ontologies

Create your own compliance rules by adding JSON files to the `ontologies/` directory.

### Ontology Structure

```json
{
  "name": "my-custom-ontology",
  "version": "1.0.0",
  "description": "Description of your ontology",
  "constraints": [
    {
      "id": "UNIQUE_ID",
      "category": "Category Name",
      "description": "What this constraint checks",
      "formula_readable": "human-readable formula",
      "variables": [
        {"name": "variable_name", "type": "bool|int|real"}
      ],
      "error_message": "Error shown when violated",
      "citation": "Reference to regulation/policy"
    }
  ],
  "extractors": {
    "variable_name": {
      "type": "boolean|int|float|money|percentage|string",
      "keywords": ["keyword1", "keyword2"],
      "pattern": "regex pattern for extraction"
    }
  }
}
```

### Extractor Types

| Type | Description | Example |
|------|-------------|---------|
| `boolean` | True if any keyword is found | `{"keywords": ["approved", "accepted"]}` |
| `int` | Extract integer from regex | `{"pattern": "score[:\\s]*(\\d+)"}` |
| `float` | Extract decimal number | `{"pattern": "(\\d+\\.\\d+)%"}` |
| `money` | Extract currency (handles k/m/b) | `{"pattern": "\\$([\\d,]+)k?"}` |
| `percentage` | Extract percentage | `{"pattern": "(\\d+(?:\\.\\d+)?)%"}` |

### Constraint Formulas

The `formula_readable` field is for documentation. The actual logic is implemented in `smt_verifier.py`. Supported patterns:

- `x ≤ value` - Less than or equal
- `x ≥ value` - Greater than or equal
- `¬x` - Negation (NOT)
- `x ∧ y` - Conjunction (AND)
- `x ∨ y` - Disjunction (OR)
- `x → y` - Implication (IF...THEN)

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | HTTP port |
| `ONTOLOGY_DIR` | `./ontologies` | Directory for custom ontologies |
| `CORS_ORIGINS` | `https://aare.ai,...` | Comma-separated allowed origins |
| `DEBUG` | `false` | Enable debug mode |

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
    volumes:
      - ./ontologies:/app/ontologies:ro
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

def verify_llm_output(llm_response: str, ontology: str = "mortgage-compliance-v1") -> dict:
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

## Cloud Deployments

For managed cloud deployments, see our cloud-specific repositories:

- [aare-aws](https://github.com/aare-ai/aare-aws) - AWS Lambda
- [aare-azure](https://github.com/aare-ai/aare-azure) - Azure Functions
- [aare-gcp](https://github.com/aare-ai/aare-gcp) - Google Cloud Functions
- [aare-watsonx](https://github.com/aare-ai/aare-watsonx) - IBM Cloud Code Engine

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- Documentation: https://aare.ai/about
- Issues: https://github.com/aare-ai/aare/issues
- Contact: info@aare.ai
