"""
aare.ai - Self-hosted verification engine
Z3 SMT theorem prover for LLM compliance verification

Run with:
    python app.py
    # or
    gunicorn --bind 0.0.0.0:8080 app:app
"""
from flask import Flask, request, jsonify
import json
import uuid
import os
from datetime import datetime

from handlers.ontology_loader import OntologyLoader
from handlers.llm_parser import LLMParser
from handlers.smt_verifier import SMTVerifier

app = Flask(__name__)

# Initialize components
ontology_loader = OntologyLoader()
llm_parser = LLMParser()
smt_verifier = SMTVerifier()

# CORS configuration from environment
ALLOWED_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "https://aare.ai,https://www.aare.ai,http://localhost:8000,http://localhost:3000"
).split(",")


def get_cors_origin(request_origin):
    """Get allowed CORS origin"""
    if request_origin in ALLOWED_ORIGINS:
        return request_origin
    if "*" in ALLOWED_ORIGINS:
        return "*"
    return ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else ""


@app.after_request
def add_cors_headers(response):
    """Add CORS headers to all responses"""
    origin = request.headers.get("Origin", "")
    response.headers["Access-Control-Allow-Origin"] = get_cors_origin(origin)
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,x-api-key,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "OPTIONS,POST,GET"
    return response


@app.route("/verify", methods=["POST", "OPTIONS"])
def verify():
    """
    HTTP endpoint for aare.ai verification

    Request body:
    {
        "llm_output": "text to verify",
        "ontology": "ontology-name-v1"
    }

    Response:
    {
        "verified": true/false,
        "violations": [...],
        "parsed_data": {...},
        "proof": {...},
        "verification_id": "uuid",
        "execution_time_ms": 45
    }
    """
    # Handle CORS preflight
    if request.method == "OPTIONS":
        return "", 204

    try:
        # Parse request body
        request_json = request.get_json(silent=True)

        if not request_json:
            return jsonify({"error": "Invalid JSON in request body"}), 400

        llm_output = request_json.get("llm_output", "")
        ontology_name = request_json.get("ontology", "mortgage-compliance-v1")

        if not llm_output:
            return jsonify({"error": "llm_output is required"}), 400

        # Load ontology
        ontology = ontology_loader.load(ontology_name)

        # Parse LLM output into structured data
        extracted_data = llm_parser.parse(llm_output, ontology)

        # Verify constraints using Z3
        verification_result = smt_verifier.verify(extracted_data, ontology)

        # Build response
        response_body = {
            "verified": verification_result["verified"],
            "violations": verification_result["violations"],
            "parsed_data": extracted_data,
            "ontology": {
                "name": ontology["name"],
                "version": ontology["version"],
                "constraints_checked": len(ontology["constraints"])
            },
            "proof": verification_result["proof"],
            "solver": "Constraint Logic",
            "verification_id": str(uuid.uuid4()),
            "execution_time_ms": verification_result["execution_time_ms"],
            "timestamp": datetime.utcnow().isoformat()
        }

        return jsonify(response_body), 200

    except Exception as e:
        return jsonify({
            "error": str(e),
            "type": type(e).__name__
        }), 500


@app.route("/ontologies", methods=["GET"])
def list_ontologies():
    """List available ontologies"""
    try:
        ontologies = ontology_loader.list_available()
        return jsonify({"ontologies": ontologies}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ontologies/<name>", methods=["GET"])
def get_ontology(name):
    """Get a specific ontology definition"""
    try:
        ontology = ontology_loader.load(name)
        return jsonify(ontology), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "aare.ai",
        "version": "1.0.0"
    }), 200


@app.route("/", methods=["GET"])
def root():
    """Root endpoint with API documentation"""
    return jsonify({
        "service": "aare.ai",
        "description": "Z3 SMT verification engine for LLM compliance",
        "version": "1.0.0",
        "endpoints": {
            "POST /verify": "Verify LLM output against compliance constraints",
            "GET /ontologies": "List available ontologies",
            "GET /ontologies/<name>": "Get ontology definition",
            "GET /health": "Health check"
        },
        "documentation": "https://github.com/aare-ai/aare"
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
