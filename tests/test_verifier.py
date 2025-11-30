"""
Basic tests for aare.ai verification engine
"""
import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handlers.llm_parser import LLMParser
from handlers.smt_verifier import SMTVerifier
from handlers.ontology_loader import OntologyLoader


@pytest.fixture
def parser():
    return LLMParser()


@pytest.fixture
def verifier():
    return SMTVerifier()


@pytest.fixture
def ontology_loader():
    return OntologyLoader()


@pytest.fixture
def default_ontology(ontology_loader):
    return ontology_loader._get_default_ontology()


class TestLLMParser:
    def test_extracts_dti(self, parser, default_ontology):
        text = "Your DTI is 35%"
        result = parser.parse(text, default_ontology)
        assert result.get("dti") == 35.0

    def test_extracts_credit_score(self, parser, default_ontology):
        text = "FICO score: 720"
        result = parser.parse(text, default_ontology)
        assert result.get("credit_score") == 720

    def test_detects_guarantee_language(self, parser, default_ontology):
        text = "You are guaranteed approval"
        result = parser.parse(text, default_ontology)
        assert result.get("has_guarantee") is True
        assert result.get("has_approval") is True


class TestSMTVerifier:
    def test_compliant_mortgage(self, verifier, default_ontology):
        data = {
            "dti": 35.0,
            "credit_score": 720,
            "compensating_factors": 0,
            "has_guarantee": False,
            "has_approval": True,
        }
        result = verifier.verify(data, default_ontology)
        assert result["verified"] is True
        assert len(result["violations"]) == 0

    def test_high_dti_violation(self, verifier, default_ontology):
        data = {
            "dti": 50.0,
            "compensating_factors": 0,
            "credit_score": 720,
        }
        result = verifier.verify(data, default_ontology)
        assert result["verified"] is False
        assert any(v["constraint_id"] == "ATR_QM_DTI" for v in result["violations"])

    def test_high_dti_with_compensating_factors(self, verifier, default_ontology):
        data = {
            "dti": 50.0,
            "compensating_factors": 2,
            "credit_score": 720,
        }
        result = verifier.verify(data, default_ontology)
        # DTI violation should not occur with 2+ compensating factors
        dti_violations = [v for v in result["violations"] if v["constraint_id"] == "ATR_QM_DTI"]
        assert len(dti_violations) == 0

    def test_guarantee_violation(self, verifier, default_ontology):
        data = {
            "has_guarantee": True,
            "has_approval": True,
            "dti": 35.0,
            "credit_score": 720,
        }
        result = verifier.verify(data, default_ontology)
        assert result["verified"] is False
        assert any(v["constraint_id"] == "UDAAP_NO_GUARANTEES" for v in result["violations"])


class TestEndToEnd:
    def test_compliant_output(self, parser, verifier, default_ontology):
        llm_output = """
        Based on your application:
        - DTI: 35%
        - FICO score: 720
        - Loan amount: $350,000

        You qualify for this mortgage based on standard underwriting criteria.
        """

        parsed = parser.parse(llm_output, default_ontology)
        result = verifier.verify(parsed, default_ontology)

        assert result["verified"] is True

    def test_violating_output(self, parser, verifier, default_ontology):
        llm_output = """
        Congratulations! You are guaranteed approved for this mortgage!
        Your DTI of 50% is no problem - we can definitely get you this loan.
        """

        parsed = parser.parse(llm_output, default_ontology)
        result = verifier.verify(parsed, default_ontology)

        assert result["verified"] is False
        assert len(result["violations"]) > 0
