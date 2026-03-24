"""PHI extractors for HIPAA guardrail."""

from .base import PHIEntity, Extractor

__all__ = ["PHIEntity", "Extractor"]


def get_distilbert_extractor():
    """Get DistilBERT extractor (default, neural NER)."""
    from .distilbert import DistilBERTExtractor
    return DistilBERTExtractor

def get_presidio_extractor():
    """Get Presidio extractor (requires presidio-analyzer)."""
    from .presidio import PresidioExtractor
    return PresidioExtractor

def get_regex_extractor():
    """Get regex extractor (lightweight fallback)."""
    from .regex import RegexExtractor
    return RegexExtractor

def get_hipaa_rules_extractor():
    """Get HIPAA rules extractor (DistilBERT + rule-based gap closure)."""
    from .hipaa_rules import HIPAARulesExtractor
    return HIPAARulesExtractor
