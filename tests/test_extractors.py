"""Tests for PHI extractors."""

import pytest
from aare.extractors.base import PHIEntity, Extractor
from aare.extractors.regex import RegexExtractor


class TestPHIEntity:
    """Tests for PHIEntity dataclass."""

    def test_create_entity(self):
        """Should create entity with all fields."""
        entity = PHIEntity(
            entity_type="SSN",
            text="123-45-6789",
            start=0,
            end=11,
            confidence=0.95
        )

        assert entity.entity_type == "SSN"
        assert entity.text == "123-45-6789"
        assert entity.start == 0
        assert entity.end == 11
        assert entity.confidence == 0.95

    def test_default_confidence(self):
        """Should default confidence to 1.0."""
        entity = PHIEntity(
            entity_type="SSN",
            text="123-45-6789",
            start=0,
            end=11
        )

        assert entity.confidence == 1.0


class TestRegexExtractor:
    """Tests for RegexExtractor."""

    def test_extract_ssn(self):
        """Should extract SSN."""
        extractor = RegexExtractor()
        entities = extractor.extract("SSN: 123-45-6789")

        assert len(entities) == 1
        assert entities[0].entity_type == "SSN"
        assert entities[0].text == "123-45-6789"

    def test_extract_phone(self):
        """Should extract phone number."""
        extractor = RegexExtractor()
        entities = extractor.extract("Call 555-123-4567")

        assert len(entities) == 1
        assert entities[0].entity_type == "PHONE_NUMBER"

    def test_extract_email(self):
        """Should extract email address."""
        extractor = RegexExtractor()
        entities = extractor.extract("Email: test@example.com")

        assert len(entities) == 1
        assert entities[0].entity_type == "EMAIL_ADDRESS"
        assert entities[0].text == "test@example.com"

    def test_extract_ip_address(self):
        """Should extract IP address."""
        extractor = RegexExtractor()
        entities = extractor.extract("Server IP: 192.168.1.100")

        assert len(entities) == 1
        assert entities[0].entity_type == "IP_ADDRESS"

    def test_extract_url(self):
        """Should extract URL."""
        extractor = RegexExtractor()
        entities = extractor.extract("Visit https://example.com/patient")

        assert len(entities) == 1
        assert entities[0].entity_type == "URL"

    def test_extract_date(self):
        """Should extract date."""
        extractor = RegexExtractor()
        entities = extractor.extract("DOB: 01/15/1985")

        assert len(entities) == 1
        assert entities[0].entity_type == "DATE"

    def test_extract_multiple(self):
        """Should extract multiple entities."""
        extractor = RegexExtractor()
        text = "SSN: 123-45-6789, Email: test@example.com"
        entities = extractor.extract(text)

        assert len(entities) == 2
        types = {e.entity_type for e in entities}
        assert "SSN" in types
        assert "EMAIL_ADDRESS" in types

    def test_no_entities(self):
        """Should return empty list for clean text."""
        extractor = RegexExtractor()
        entities = extractor.extract("The patient has hypertension.")

        assert len(entities) == 0

    def test_entities_sorted_by_position(self):
        """Entities should be sorted by position."""
        extractor = RegexExtractor()
        text = "Email test@example.com then SSN 123-45-6789"
        entities = extractor.extract(text)

        # Should be sorted by start position
        positions = [e.start for e in entities]
        assert positions == sorted(positions)

    def test_confidence_score(self):
        """Should have confidence score."""
        extractor = RegexExtractor()
        entities = extractor.extract("SSN: 123-45-6789")

        assert entities[0].confidence == 0.9  # Regex default


class TestExtractorProtocol:
    """Tests for Extractor protocol."""

    def test_regex_extractor_is_extractor(self):
        """RegexExtractor should satisfy Extractor protocol."""
        extractor = RegexExtractor()
        assert isinstance(extractor, Extractor)

    def test_custom_extractor(self):
        """Custom class implementing protocol should work."""

        class CustomExtractor:
            def extract(self, text: str):
                return [PHIEntity("CUSTOM", "test", 0, 4, 1.0)]

        extractor = CustomExtractor()
        assert isinstance(extractor, Extractor)
        entities = extractor.extract("test")
        assert len(entities) == 1
