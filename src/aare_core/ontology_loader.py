"""
Ontology loader for aare.ai (Self-hosted version)
Loads verification rules from local filesystem or returns example default
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
        # Bundled ontologies directory (shipped with package)
        self._bundled_dir = Path(__file__).parent / "ontologies"

    @lru_cache(maxsize=10)
    def load(self, ontology_name):
        """Load ontology from filesystem, bundled package, or return default"""
        # First check user-specified directory
        ontology_file = self.ontology_dir / f"{ontology_name}.json"

        # Then check bundled ontologies
        bundled_file = self._bundled_dir / f"{ontology_name}.json"

        try:
            if ontology_file.exists():
                with open(ontology_file, "r") as f:
                    ontology = json.load(f)
                return self._validate_ontology(ontology)
            elif bundled_file.exists():
                with open(bundled_file, "r") as f:
                    ontology = json.load(f)
                return self._validate_ontology(ontology)
        except Exception as e:
            logging.warning(f"Failed to load ontology {ontology_name}: {e}")

        # Fall back to example ontology
        logging.info(f"Using example ontology for {ontology_name}")
        return self._get_example_ontology()

    # Valid variable types for Z3
    VALID_VAR_TYPES = {'bool', 'int', 'real', 'float'}
    # Maximum formula nesting depth to prevent resource exhaustion
    MAX_FORMULA_DEPTH = 50

    def _validate_ontology(self, ontology):
        """Validate ontology structure with type checking and depth limits"""
        required_fields = ["name", "version", "constraints"]
        for field in required_fields:
            if field not in ontology:
                raise ValueError(f"Invalid ontology: missing {field}")

        # Type check: constraints must be a list
        if not isinstance(ontology.get("constraints"), list):
            raise ValueError("Invalid ontology: 'constraints' must be a list")

        # Validate each constraint
        for constraint in ontology["constraints"]:
            if not isinstance(constraint, dict):
                raise ValueError("Invalid ontology: each constraint must be a dict")

            constraint_id = constraint.get('id', 'unknown')

            if "formula" not in constraint:
                raise ValueError(
                    f"Invalid ontology: constraint {constraint_id} missing 'formula' field"
                )

            # Validate formula depth
            self._validate_formula_depth(constraint["formula"], 0, constraint_id)

            # Validate variables
            variables = constraint.get("variables", [])
            if not isinstance(variables, list):
                raise ValueError(
                    f"Invalid ontology: constraint {constraint_id} 'variables' must be a list"
                )

            for var in variables:
                if not isinstance(var, dict):
                    raise ValueError(
                        f"Invalid ontology: constraint {constraint_id} variable must be a dict"
                    )
                if "name" not in var or "type" not in var:
                    raise ValueError(
                        f"Invalid ontology: constraint {constraint_id} variable missing 'name' or 'type'"
                    )
                if var["type"] not in self.VALID_VAR_TYPES:
                    raise ValueError(
                        f"Invalid ontology: constraint {constraint_id} variable '{var['name']}' "
                        f"has invalid type '{var['type']}'. Must be one of: {self.VALID_VAR_TYPES}"
                    )

        return ontology

    def _validate_formula_depth(self, formula, current_depth, constraint_id):
        """Recursively validate formula depth to prevent resource exhaustion"""
        if current_depth > self.MAX_FORMULA_DEPTH:
            raise ValueError(
                f"Invalid ontology: constraint {constraint_id} formula exceeds "
                f"maximum depth of {self.MAX_FORMULA_DEPTH}"
            )

        if isinstance(formula, dict):
            for key, value in formula.items():
                if isinstance(value, list):
                    for item in value:
                        self._validate_formula_depth(item, current_depth + 1, constraint_id)
                elif isinstance(value, dict):
                    self._validate_formula_depth(value, current_depth + 1, constraint_id)

    def _get_example_ontology(self):
        """
        Return example ontology demonstrating the framework.

        This is a generic example showing how to define constraints.
        For production use, create your own ontology JSON files in the ontologies/ directory.
        """
        return {
            "name": "example",
            "version": "1.0.0",
            "description": "Example ontology demonstrating constraint syntax",
            "constraints": [
                {
                    "id": "MAX_VALUE",
                    "category": "Limits",
                    "description": "Value must not exceed maximum",
                    "formula_readable": "value <= 100",
                    "formula": {"<=": ["value", 100]},
                    "variables": [{"name": "value", "type": "real"}],
                    "error_message": "Value exceeds maximum allowed (100)",
                    "citation": "Example Policy",
                },
                {
                    "id": "MIN_VALUE",
                    "category": "Limits",
                    "description": "Value must meet minimum threshold",
                    "formula_readable": "value >= 0",
                    "formula": {">=": ["value", 0]},
                    "variables": [{"name": "value", "type": "real"}],
                    "error_message": "Value below minimum threshold (0)",
                    "citation": "Example Policy",
                },
                {
                    "id": "NO_PROHIBITED_FLAG",
                    "category": "Compliance",
                    "description": "Prohibited flag must not be set",
                    "formula_readable": "!prohibited",
                    "formula": {"==": ["prohibited", False]},
                    "variables": [{"name": "prohibited", "type": "bool"}],
                    "error_message": "Prohibited action detected",
                    "citation": "Example Policy",
                },
                {
                    "id": "CONDITIONAL_REQUIREMENT",
                    "category": "Logic",
                    "description": "If condition A, then condition B must be true",
                    "formula_readable": "condition_a -> condition_b",
                    "formula": {
                        "implies": [
                            {"==": ["condition_a", True]},
                            {"==": ["condition_b", True]},
                        ]
                    },
                    "variables": [
                        {"name": "condition_a", "type": "bool"},
                        {"name": "condition_b", "type": "bool"},
                    ],
                    "error_message": "Condition B required when Condition A is true",
                    "citation": "Example Policy",
                },
                {
                    "id": "EITHER_OR_REQUIREMENT",
                    "category": "Logic",
                    "description": "At least one option must be selected",
                    "formula_readable": "option_a || option_b",
                    "formula": {
                        "or": [
                            {"==": ["option_a", True]},
                            {"==": ["option_b", True]},
                        ]
                    },
                    "variables": [
                        {"name": "option_a", "type": "bool"},
                        {"name": "option_b", "type": "bool"},
                    ],
                    "error_message": "At least one option must be selected",
                    "citation": "Example Policy",
                },
            ],
            "extractors": {
                "value": {"type": "float", "pattern": "value[:\\s]*(\\d+(?:\\.\\d+)?)"},
                "prohibited": {
                    "type": "boolean",
                    "keywords": ["prohibited", "forbidden", "banned"],
                },
                "condition_a": {"type": "boolean", "keywords": ["condition a", "case a"]},
                "condition_b": {"type": "boolean", "keywords": ["condition b", "case b"]},
                "option_a": {"type": "boolean", "keywords": ["option a", "choice a"]},
                "option_b": {"type": "boolean", "keywords": ["option b", "choice b"]},
            },
        }

    def list_available(self):
        """List all available ontologies"""
        ontologies = set(["example"])

        # Add bundled ontologies
        if self._bundled_dir.exists():
            for f in self._bundled_dir.glob("*.json"):
                ontologies.add(f.stem)

        # Add any from the user ontology directory
        if self.ontology_dir.exists():
            for f in self.ontology_dir.glob("*.json"):
                ontologies.add(f.stem)

        return sorted(list(ontologies))
