"""
Ontology loader for aare.ai (Self-hosted version)
Loads verification rules from local filesystem or returns defaults
"""
import json
import os
import logging
from functools import lru_cache
from pathlib import Path


class OntologyLoader:
    def __init__(self, ontology_dir=None):
        self.ontology_dir = Path(
            ontology_dir or os.environ.get("ONTOLOGY_DIR", "./ontologies")
        )

    @lru_cache(maxsize=10)
    def load(self, ontology_name):
        """Load ontology from filesystem or return default"""
        ontology_file = self.ontology_dir / f"{ontology_name}.json"

        try:
            if ontology_file.exists():
                with open(ontology_file, "r") as f:
                    ontology = json.load(f)
                return self._validate_ontology(ontology)
        except Exception as e:
            logging.warning(f"Failed to load ontology from {ontology_file}: {e}")

        # Check for built-in ontologies
        builtin = self._get_builtin_ontology(ontology_name)
        if builtin:
            return builtin

        # Fall back to default
        logging.info(f"Using default ontology for {ontology_name}")
        return self._get_default_ontology()

    def _validate_ontology(self, ontology):
        """Validate ontology structure"""
        required_fields = ["name", "version", "constraints", "extractors"]
        for field in required_fields:
            if field not in ontology:
                raise ValueError(f"Invalid ontology: missing {field}")
        return ontology

    def _get_builtin_ontology(self, name):
        """Get built-in ontology by name"""
        builtins = {
            "mortgage-compliance-v1": self._get_default_ontology(),
            "fair-lending-v1": self._get_fair_lending_ontology(),
            "hipaa-v1": self._get_hipaa_ontology(),
        }
        return builtins.get(name)

    def _get_default_ontology(self):
        """Return default mortgage compliance ontology"""
        return {
            "name": "mortgage-compliance-v1",
            "version": "1.0.0",
            "description": "U.S. Mortgage Compliance - Core constraints",
            "constraints": [
                {
                    "id": "ATR_QM_DTI",
                    "category": "ATR/QM",
                    "description": "Debt-to-income ratio requirements",
                    "formula_readable": "(dti ≤ 43) ∨ (compensating_factors ≥ 2)",
                    "variables": [
                        {"name": "dti", "type": "real"},
                        {"name": "compensating_factors", "type": "int"},
                    ],
                    "error_message": "DTI exceeds 43% without sufficient compensating factors",
                    "citation": "12 CFR § 1026.43(c)",
                },
                {
                    "id": "HOEPA_HIGH_COST",
                    "category": "HOEPA",
                    "description": "High-cost mortgage counseling requirement",
                    "formula_readable": "(fee_percentage < 8) ∨ counseling_disclosed",
                    "variables": [
                        {"name": "fee_percentage", "type": "real"},
                        {"name": "counseling_disclosed", "type": "bool"},
                    ],
                    "error_message": "HOEPA triggered - counseling disclosure required",
                    "citation": "12 CFR § 1026.32",
                },
                {
                    "id": "UDAAP_NO_GUARANTEES",
                    "category": "UDAAP",
                    "description": "Prohibition on guarantee language",
                    "formula_readable": "¬(has_guarantee ∧ has_approval)",
                    "variables": [
                        {"name": "has_guarantee", "type": "bool"},
                        {"name": "has_approval", "type": "bool"},
                    ],
                    "error_message": "Cannot guarantee approval",
                    "citation": "12 CFR § 1036.3",
                },
                {
                    "id": "HPML_ESCROW",
                    "category": "Escrow",
                    "description": "Escrow requirements based on FICO",
                    "formula_readable": "(credit_score ≥ 620) ∨ ¬escrow_waived",
                    "variables": [
                        {"name": "credit_score", "type": "int"},
                        {"name": "escrow_waived", "type": "bool"},
                    ],
                    "error_message": "Cannot waive escrow with FICO < 620",
                    "citation": "12 CFR § 1026.35(b)",
                },
                {
                    "id": "REG_B_ADVERSE",
                    "category": "Regulation B",
                    "description": "Adverse action disclosure requirements",
                    "formula_readable": "is_denial → has_specific_reason",
                    "variables": [
                        {"name": "is_denial", "type": "bool"},
                        {"name": "has_specific_reason", "type": "bool"},
                    ],
                    "error_message": "Must disclose specific denial reason",
                    "citation": "12 CFR § 1002.9",
                },
            ],
            "extractors": {
                "dti": {"type": "float", "pattern": "dti[:\\s~]*(\\d+(?:\\.\\d+)?)"},
                "credit_score": {
                    "type": "int",
                    "pattern": "(?:fico|credit score)[:\\s]*(\\d{3})",
                },
                "fees": {
                    "type": "money",
                    "pattern": "\\$?([\\d,]+)k?\\s*(?:fees?|costs?)",
                },
                "loan_amount": {
                    "type": "money",
                    "pattern": "\\$?([\\d,]+)k?\\s*(?:loan|mortgage)",
                },
                "has_guarantee": {
                    "type": "boolean",
                    "keywords": ["guaranteed", "100%", "definitely"],
                },
                "has_approval": {"type": "boolean", "keywords": ["approved", "approve"]},
                "counseling_disclosed": {
                    "type": "boolean",
                    "keywords": ["counseling"],
                },
                "escrow_waived": {
                    "type": "boolean",
                    "keywords": ["escrow waived", "waive escrow", "skip escrow"],
                },
                "is_denial": {
                    "type": "boolean",
                    "keywords": ["denied", "cannot approve"],
                },
                "has_specific_reason": {
                    "type": "boolean",
                    "keywords": ["credit", "income", "dti", "debt", "score"],
                },
            },
        }

    def _get_fair_lending_ontology(self):
        """Return fair lending ontology"""
        return {
            "name": "fair-lending-v1",
            "version": "1.0.0",
            "description": "Fair Lending Compliance",
            "constraints": [
                {
                    "id": "LOAN_AMOUNT_LIMIT",
                    "category": "Fair Lending",
                    "description": "Loan amount within policy limits",
                    "formula_readable": "loan_amount ≤ 100000",
                    "variables": [{"name": "loan_amount", "type": "int"}],
                    "error_message": "Loan amount exceeds policy limit",
                    "citation": "Internal Policy",
                },
                {
                    "id": "MAX_DTI",
                    "category": "Fair Lending",
                    "description": "Maximum DTI ratio",
                    "formula_readable": "dti ≤ 43",
                    "variables": [{"name": "dti", "type": "real"}],
                    "error_message": "DTI exceeds maximum",
                    "citation": "12 CFR § 1026.43",
                },
                {
                    "id": "MIN_CREDIT_SCORE",
                    "category": "Fair Lending",
                    "description": "Minimum credit score requirement",
                    "formula_readable": "credit_score ≥ 600",
                    "variables": [{"name": "credit_score", "type": "int"}],
                    "error_message": "Credit score below minimum",
                    "citation": "Internal Policy",
                },
            ],
            "extractors": {
                "loan_amount": {
                    "type": "money",
                    "pattern": "\\$?([\\d,]+)k?\\s*(?:loan|mortgage)",
                },
                "dti": {"type": "float", "pattern": "dti[:\\s~]*(\\d+(?:\\.\\d+)?)"},
                "credit_score": {
                    "type": "int",
                    "pattern": "(?:fico|credit score)[:\\s]*(\\d{3})",
                },
            },
        }

    def _get_hipaa_ontology(self):
        """Return HIPAA compliance ontology"""
        return {
            "name": "hipaa-v1",
            "version": "1.0.0",
            "description": "HIPAA PHI Protection",
            "constraints": [
                {
                    "id": "PHI_SSN_ZERO_TOLERANCE",
                    "category": "PHI Detection",
                    "description": "No SSN disclosure",
                    "formula_readable": "¬has_ssn",
                    "variables": [{"name": "has_ssn", "type": "bool"}],
                    "error_message": "SSN detected in output",
                    "citation": "45 CFR § 164.514",
                },
                {
                    "id": "PHI_NAME_DISCLOSURE",
                    "category": "PHI Detection",
                    "description": "Patient name requires authorization",
                    "formula_readable": "¬has_patient_name ∨ recipient_authorized",
                    "variables": [
                        {"name": "has_patient_name", "type": "bool"},
                        {"name": "recipient_authorized", "type": "bool"},
                    ],
                    "error_message": "Patient name disclosed without authorization",
                    "citation": "45 CFR § 164.502",
                },
                {
                    "id": "PHI_ADDRESS_DISCLOSURE",
                    "category": "PHI Detection",
                    "description": "No street address disclosure",
                    "formula_readable": "¬has_street_address",
                    "variables": [{"name": "has_street_address", "type": "bool"}],
                    "error_message": "Street address detected in output",
                    "citation": "45 CFR § 164.514",
                },
            ],
            "extractors": {
                "has_ssn": {
                    "type": "boolean",
                    "keywords": [],
                    "pattern": "\\d{3}-\\d{2}-\\d{4}",
                },
                "has_patient_name": {
                    "type": "boolean",
                    "keywords": ["patient:", "name:"],
                },
                "has_street_address": {
                    "type": "boolean",
                    "keywords": ["street", "avenue", "blvd", "road", "lane"],
                },
                "recipient_authorized": {
                    "type": "boolean",
                    "keywords": ["authorized", "consent"],
                },
            },
        }

    def list_available(self):
        """List all available ontologies"""
        ontologies = set(["mortgage-compliance-v1", "fair-lending-v1", "hipaa-v1"])

        # Add any from the ontology directory
        if self.ontology_dir.exists():
            for f in self.ontology_dir.glob("*.json"):
                ontologies.add(f.stem)

        return sorted(list(ontologies))
