"""Tests for DistilBERT PHI extractor."""

import pytest
from unittest.mock import patch, MagicMock

from aare.extractors.base import PHIEntity
from aare.extractors.distilbert import DistilBERTExtractor, LABEL_TO_HIPAA, DEFAULT_MODEL


class TestLabelMapping:
    """Test label mapping covers all HIPAA Safe Harbor categories."""

    def test_all_18_categories_mapped(self):
        expected_hipaa_types = {
            "NAMES", "GEOGRAPHIC_SUBDIVISIONS", "DATES",
            "PHONE_NUMBERS", "FAX_NUMBERS", "EMAIL_ADDRESSES",
            "SSN", "MEDICAL_RECORD_NUMBERS", "HEALTH_PLAN_BENEFICIARY_NUMBERS",
            "ACCOUNT_NUMBERS", "CERTIFICATE_LICENSE_NUMBERS",
            "VEHICLE_IDENTIFIERS", "DEVICE_IDENTIFIERS",
            "WEB_URLS", "IP_ADDRESSES", "BIOMETRIC_IDENTIFIERS",
            "PHOTOGRAPHIC_IMAGES", "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER",
        }
        assert set(LABEL_TO_HIPAA.values()) == expected_hipaa_types

    def test_label_mapping_keys(self):
        assert LABEL_TO_HIPAA["NAME"] == "NAMES"
        assert LABEL_TO_HIPAA["SSN"] == "SSN"
        assert LABEL_TO_HIPAA["EMAIL"] == "EMAIL_ADDRESSES"
        assert LABEL_TO_HIPAA["PHONE"] == "PHONE_NUMBERS"


class TestDistilBERTExtractor:
    """Test DistilBERT extractor with mocked pipeline."""

    @pytest.fixture
    def mock_pipeline(self):
        with patch("aare.extractors.distilbert._hf_pipeline") as mock_pl:
            mock_pipe = MagicMock()
            mock_pl.return_value = mock_pipe
            yield mock_pipe, mock_pl

    def test_init_default_model(self, mock_pipeline):
        mock_pipe, mock_pl = mock_pipeline
        ext = DistilBERTExtractor()
        mock_pl.assert_called_once_with(
            "token-classification",
            model=DEFAULT_MODEL,
            aggregation_strategy="simple",
            device=-1,
        )

    def test_init_custom_model_path(self, mock_pipeline):
        mock_pipe, mock_pl = mock_pipeline
        ext = DistilBERTExtractor(model_path="/custom/model")
        mock_pl.assert_called_once_with(
            "token-classification",
            model="/custom/model",
            aggregation_strategy="simple",
            device=-1,
        )

    def test_extract_empty_string(self, mock_pipeline):
        mock_pipe, _ = mock_pipeline
        ext = DistilBERTExtractor()
        assert ext.extract("") == []
        assert ext.extract("   ") == []
        mock_pipe.assert_not_called()

    def test_extract_ssn(self, mock_pipeline):
        mock_pipe, _ = mock_pipeline
        mock_pipe.return_value = [
            {
                "entity_group": "SSN",
                "score": 0.95,
                "word": "123-45-6789",
                "start": 5,
                "end": 16,
            }
        ]
        ext = DistilBERTExtractor()
        entities = ext.extract("SSN: 123-45-6789")

        assert len(entities) == 1
        assert entities[0].entity_type == "SSN"
        assert entities[0].text == "123-45-6789"
        assert entities[0].start == 5
        assert entities[0].end == 16
        assert entities[0].confidence == 0.95

    def test_extract_name(self, mock_pipeline):
        mock_pipe, _ = mock_pipeline
        mock_pipe.return_value = [
            {
                "entity_group": "NAME",
                "score": 0.92,
                "word": "John Smith",
                "start": 8,
                "end": 18,
            }
        ]
        ext = DistilBERTExtractor()
        entities = ext.extract("Patient John Smith")

        assert len(entities) == 1
        assert entities[0].entity_type == "NAMES"
        assert entities[0].text == "John Smith"

    def test_extract_multiple_entities(self, mock_pipeline):
        mock_pipe, _ = mock_pipeline
        mock_pipe.return_value = [
            {
                "entity_group": "NAME",
                "score": 0.92,
                "word": "John Smith",
                "start": 8,
                "end": 18,
            },
            {
                "entity_group": "SSN",
                "score": 0.97,
                "word": "123-45-6789",
                "start": 25,
                "end": 36,
            },
            {
                "entity_group": "EMAIL",
                "score": 0.88,
                "word": "john@example.com",
                "start": 44,
                "end": 60,
            },
        ]
        ext = DistilBERTExtractor()
        entities = ext.extract("Patient John Smith, SSN: 123-45-6789, email: john@example.com")

        assert len(entities) == 3
        assert entities[0].entity_type == "NAMES"
        assert entities[1].entity_type == "SSN"
        assert entities[2].entity_type == "EMAIL_ADDRESSES"

    def test_confidence_threshold_filters(self, mock_pipeline):
        mock_pipe, _ = mock_pipeline
        mock_pipe.return_value = [
            {
                "entity_group": "NAME",
                "score": 0.3,  # Below default threshold of 0.5
                "word": "Jackson",
                "start": 4,
                "end": 11,
            },
            {
                "entity_group": "SSN",
                "score": 0.95,
                "word": "123-45-6789",
                "start": 20,
                "end": 31,
            },
        ]
        ext = DistilBERTExtractor()
        entities = ext.extract("The Jackson procedure, SSN 123-45-6789")

        assert len(entities) == 1
        assert entities[0].entity_type == "SSN"

    def test_custom_confidence_threshold(self, mock_pipeline):
        mock_pipe, _ = mock_pipeline
        mock_pipe.return_value = [
            {
                "entity_group": "NAME",
                "score": 0.75,
                "word": "Smith",
                "start": 0,
                "end": 5,
            },
        ]
        ext = DistilBERTExtractor(confidence_threshold=0.8)
        entities = ext.extract("Smith")
        assert len(entities) == 0

        ext2 = DistilBERTExtractor(confidence_threshold=0.7)
        entities2 = ext2.extract("Smith")
        assert len(entities2) == 1

    def test_unknown_label_passed_through(self, mock_pipeline):
        mock_pipe, _ = mock_pipeline
        mock_pipe.return_value = [
            {
                "entity_group": "UNKNOWN_TYPE",
                "score": 0.9,
                "word": "xyz",
                "start": 0,
                "end": 3,
            },
        ]
        ext = DistilBERTExtractor()
        entities = ext.extract("xyz")

        assert len(entities) == 1
        assert entities[0].entity_type == "UNKNOWN_TYPE"

    def test_returns_phi_entity_instances(self, mock_pipeline):
        mock_pipe, _ = mock_pipeline
        mock_pipe.return_value = [
            {
                "entity_group": "PHONE",
                "score": 0.85,
                "word": "555-0123",
                "start": 7,
                "end": 15,
            },
        ]
        ext = DistilBERTExtractor()
        entities = ext.extract("Phone: 555-0123")

        assert isinstance(entities[0], PHIEntity)
        assert entities[0].entity_type == "PHONE_NUMBERS"


class TestGuardrailIntegration:
    """Test DistilBERT extractor integrates with HIPAAGuardrail."""

    @pytest.fixture
    def mock_pipeline(self):
        with patch("aare.extractors.distilbert._hf_pipeline") as mock_pl:
            mock_pipe = MagicMock()
            mock_pl.return_value = mock_pipe
            yield mock_pipe

    def test_guardrail_uses_regex_by_default(self, mock_pipeline):
        from aare.guardrail import HIPAAGuardrail
        from aare.extractors.regex import RegexExtractor
        guardrail = HIPAAGuardrail()
        assert isinstance(guardrail._extractor, RegexExtractor)

    def test_guardrail_blocks_phi(self, mock_pipeline):
        mock_pipeline.return_value = [
            {
                "entity_group": "SSN",
                "score": 0.97,
                "word": "123-45-6789",
                "start": 5,
                "end": 16,
            },
        ]
        from aare.guardrail import HIPAAGuardrail
        guardrail = HIPAAGuardrail(on_violation="block")
        result = guardrail.check("SSN: 123-45-6789")
        assert result.blocked

    def test_guardrail_passes_clean_text(self, mock_pipeline):
        mock_pipeline.return_value = []
        from aare.guardrail import HIPAAGuardrail
        guardrail = HIPAAGuardrail()
        result = guardrail.check("The patient should follow up in 7 days.")
        assert result.passed

    def test_create_guardrail_distilbert(self, mock_pipeline):
        from aare.guardrail import create_guardrail
        guardrail = create_guardrail(extractor="distilbert")
        assert isinstance(guardrail._extractor, DistilBERTExtractor)

    def test_create_guardrail_regex_fallback(self):
        from aare.guardrail import create_guardrail
        from aare.extractors.regex import RegexExtractor
        guardrail = create_guardrail(extractor="regex")
        assert isinstance(guardrail._extractor, RegexExtractor)
