"""DistilBERT-based PHI extractor for HIPAA compliance.

Uses a fine-tuned DistilBERT model trained on all 18 HIPAA Safe Harbor
categories with BIO token classification.
"""

from __future__ import annotations

from typing import List, Optional

from transformers import pipeline as _hf_pipeline

from .base import Extractor, PHIEntity


# Map model output labels to HIPAA category names used by HIPAARules
LABEL_TO_HIPAA = {
    "NAME": "NAMES",
    "LOCATION": "GEOGRAPHIC_SUBDIVISIONS",
    "DATE": "DATES",
    "PHONE": "PHONE_NUMBERS",
    "FAX": "FAX_NUMBERS",
    "EMAIL": "EMAIL_ADDRESSES",
    "SSN": "SSN",
    "MRN": "MEDICAL_RECORD_NUMBERS",
    "HEALTH_PLAN": "HEALTH_PLAN_BENEFICIARY_NUMBERS",
    "ACCOUNT": "ACCOUNT_NUMBERS",
    "LICENSE": "CERTIFICATE_LICENSE_NUMBERS",
    "VEHICLE": "VEHICLE_IDENTIFIERS",
    "DEVICE": "DEVICE_IDENTIFIERS",
    "URL": "WEB_URLS",
    "IP": "IP_ADDRESSES",
    "BIOMETRIC": "BIOMETRIC_IDENTIFIERS",
    "PHOTO": "PHOTOGRAPHIC_IMAGES",
    "OTHER": "ANY_OTHER_UNIQUE_IDENTIFYING_NUMBER",
}

DEFAULT_MODEL = "mkocher/hipaa-phi-detector"


class DistilBERTExtractor(Extractor):
    """PHI extractor using a fine-tuned DistilBERT NER model.

    This extractor uses a DistilBERT model trained on all 18 HIPAA Safe Harbor
    categories for token-level PHI detection. Unlike regex, it understands context
    (e.g., "Jackson procedure" is not a name).

    Args:
        model_path: Path to local model directory or HuggingFace Hub model ID.
            Defaults to "aare-ai/hipaa-phi-detector".
        confidence_threshold: Minimum confidence score to include an entity.
            Defaults to 0.5.
        device: Device for inference ("cpu", "cuda", "mps", or -1/0/etc).
            Defaults to -1 (CPU).
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence_threshold: float = 0.5,
        device: int = -1,
    ):
        self.confidence_threshold = confidence_threshold
        self._model_path = model_path or DEFAULT_MODEL

        self._pipeline = _hf_pipeline(
            "token-classification",
            model=self._model_path,
            aggregation_strategy="simple",
            device=device,
        )

    def extract(self, text: str) -> List[PHIEntity]:
        """Extract PHI entities from text using DistilBERT.

        Args:
            text: Input text to analyze.

        Returns:
            List of detected PHI entities with HIPAA category labels.
        """
        if not text or not text.strip():
            return []

        results = self._pipeline(text)

        entities = []
        for result in results:
            score = result["score"]
            if score < self.confidence_threshold:
                continue

            # The pipeline returns entity_group like "NAME", "SSN", etc.
            raw_label = result["entity_group"]

            # Map to HIPAA category name
            entity_type = LABEL_TO_HIPAA.get(raw_label, raw_label)

            entities.append(PHIEntity(
                entity_type=entity_type,
                text=result["word"],
                start=result["start"],
                end=result["end"],
                confidence=score,
            ))

        return entities
