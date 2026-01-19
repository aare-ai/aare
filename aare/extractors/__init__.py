"""PHI extractors for HIPAA guardrail."""

from .base import PHIEntity, Extractor

__all__ = ["PHIEntity", "Extractor"]

# Lazy imports for optional extractors
def get_presidio_extractor():
    """Get Presidio extractor (requires presidio-analyzer)."""
    from .presidio import PresidioExtractor
    return PresidioExtractor

def get_regex_extractor():
    """Get regex extractor (no dependencies)."""
    from .regex import RegexExtractor
    return RegexExtractor
