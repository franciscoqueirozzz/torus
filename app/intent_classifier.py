"""Vetorização e inferência do classificador de intenção comercial."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = BACKEND_ROOT / "models"
MODEL_PATH = MODEL_DIR / "intent_classifier.json"
METADATA_PATH = MODEL_DIR / "model_metadata.json"


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    only_words = re.sub(r"[^a-z0-9\s]", " ", without_accents.lower())
    return re.sub(r"\s+", " ", only_words).strip()


def text_features(text: str) -> Counter[str]:
    normalized = normalize_text(text)
    tokens = normalized.split()

    features = [f"w:{token}" for token in tokens]
    features.extend(f"b:{left}__{right}" for left, right in pairwise(tokens))

    # Os n-gramas de caracteres reduzem o impacto de pequenas variações de escrita.
    padded_text = f" {normalized} "
    for size in (3, 4, 5):
        features.extend(
            f"c:{padded_text[start : start + size]}"
            for start in range(len(padded_text) - size + 1)
        )
    return Counter(features)


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    largest_score = max(scores.values())
    exponentials = {
        label: math.exp(score - largest_score) for label, score in scores.items()
    }
    total = sum(exponentials.values()) or 1.0
    return {label: value / total for label, value in exponentials.items()}


def _logistic_probabilities(
    model: dict[str, Any],
    text: str,
) -> dict[str, float]:
    counts = text_features(text)
    largest_count = max(counts.values(), default=1)
    vector = {
        feature: count / largest_count * float(model["idf"][feature])
        for feature, count in counts.items()
        if feature in model["idf"]
    }

    scores = {}
    for label in model["labels"]:
        weighted_sum = sum(
            float(model["weights"][label].get(feature, 0.0)) * value
            for feature, value in vector.items()
        )
        scores[label] = float(model["biases"][label]) + weighted_sum
    return _softmax(scores)


def predict_probabilities(
    model: dict[str, Any],
    text: str,
) -> dict[str, float]:
    model_type = model.get("model_type")
    if model_type == "logistic_regression":
        return _logistic_probabilities(model, text)
    raise ValueError(f"Tipo de modelo não reconhecido: {model_type!r}")


@lru_cache(maxsize=1)
def load_model() -> dict[str, Any] | None:
    if not MODEL_PATH.exists():
        return None
    return json.loads(MODEL_PATH.read_text(encoding="utf-8"))


def predict_intent(text: str) -> dict[str, Any]:
    model = load_model()
    if model is None:
        raise RuntimeError(
            "Modelo não encontrado. Restaure backend/models/intent_classifier.json "
            "a partir de uma cópia íntegra do projeto e reinicie o servidor."
        )

    if not normalize_text(text):
        return {
            "label": "neutral",
            "confidence": 1.0,
            "model": model["model_type"],
            "probabilities": {"neutral": 1.0},
        }

    probabilities = predict_probabilities(model, text)
    predicted_label = max(probabilities, key=probabilities.get)
    return {
        "label": predicted_label,
        "confidence": round(probabilities[predicted_label], 4),
        "model": model["model_type"],
        "probabilities": {
            label: round(probability, 4) for label, probability in probabilities.items()
        },
    }


def get_model_metadata() -> dict[str, Any]:
    return json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def clear_model_cache() -> None:
    load_model.cache_clear()
