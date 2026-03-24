"""ML-based prompt injection detector.

Uses a pre-trained HuggingFace text classification model to detect
prompt injection and jailbreak attacks.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .base import Detector, InjectionThreat

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "protectai/deberta-v3-base-prompt-injection-v2"

# Map model output labels to threat types
LABEL_TO_THREAT_TYPE = {
    "INJECTION": "prompt_injection",
    "injection": "prompt_injection",
    "JAILBREAK": "jailbreak",
    "jailbreak": "jailbreak",
    # The protectai model uses "INJECTION" as the positive label
}


class InjectionClassifier:
    """Prompt injection detector using a pre-trained text classification model.

    Uses a HuggingFace text-classification pipeline to detect prompt injection
    and jailbreak attacks. The model is loaded lazily on first use.

    Args:
        model_name: HuggingFace model ID or local path.
            Defaults to "protectai/deberta-v3-base-prompt-injection-v2".
        confidence_threshold: Minimum confidence to flag as a threat.
            Defaults to 0.75.
        device: Device for inference (-1 = CPU, 0 = first GPU, etc).
            Defaults to -1 (CPU).
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        confidence_threshold: float = 0.75,
        device: int = -1,
    ):
        self._model_name = model_name or DEFAULT_MODEL
        self.confidence_threshold = confidence_threshold
        self._device = device
        self._pipeline = None

    def preload(self) -> None:
        """Eagerly load the model into memory.

        Call this at application startup to avoid latency on first detection.
        """
        self._ensure_pipeline()

    def _ensure_pipeline(self):
        """Lazily initialize the HuggingFace pipeline."""
        if self._pipeline is not None:
            return

        from transformers import pipeline as _hf_pipeline

        self._pipeline = _hf_pipeline(
            "text-classification",
            model=self._model_name,
            device=self._device,
        )

    def detect(self, text: str) -> List[InjectionThreat]:
        """Detect prompt injection threats in text.

        Args:
            text: Input text to analyze.

        Returns:
            List of detected injection threats. Empty if text is clean.
        """
        if not text or not text.strip():
            return []

        self._ensure_pipeline()

        # Truncate to model max length to avoid errors
        results = self._pipeline(text, truncation=True)

        threats = []
        for result in results:
            label = result["label"]
            score = result["score"]

            # The model outputs INJECTION/SAFE (or similar binary labels).
            # We only care about the injection-positive label.
            threat_type = LABEL_TO_THREAT_TYPE.get(label)

            if threat_type is None:
                # This is the "safe" / "benign" label — skip
                continue

            if score < self.confidence_threshold:
                logger.debug(
                    "Injection score %.3f below threshold %.3f, skipping",
                    score, self.confidence_threshold,
                )
                continue

            threats.append(InjectionThreat(
                threat_type=threat_type,
                text=text,
                start=0,
                end=len(text),
                confidence=score,
                description=(
                    f"Detected {threat_type} with confidence {score:.2f} "
                    f"using model {self._model_name}"
                ),
            ))

        return threats
