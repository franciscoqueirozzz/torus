"""Processamento de cada fala antes da consolidação da reunião."""

from __future__ import annotations

import re
from typing import Any

from app.intent_classifier import predict_intent

TOTVS_PRODUCTS = {
    "protheus": "Protheus",
    "rm": "RM",
    "fluig": "Fluig",
    "datasul": "Datasul",
    "logix": "Logix",
}

POSITIVE_TERMS = {
    "bom",
    "bons resultados",
    "deu certo",
    "eficiente",
    "excelente",
    "feliz",
    "funcionando bem",
    "gostei",
    "melhorou",
    "ótimo",
    "satisfeito",
    "sucesso",
}

NEGATIVE_TERMS = {
    "cancelamento",
    "cancelar",
    "caro",
    "encerrar",
    "insatisfeito",
    "instável",
    "pessimo",
    "péssimo",
    "problema",
    "ruim",
    "sair",
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def analyze_sentiment(text: str) -> dict[str, Any]:
    normalized = clean_text(text)
    positive_hits = sum(term in normalized for term in POSITIVE_TERMS)
    negative_hits = sum(term in normalized for term in NEGATIVE_TERMS)

    if positive_hits == negative_hits:
        return {"label": "neutral", "score": 0.5}

    difference = abs(positive_hits - negative_hits)
    confidence = min(0.95, 0.65 + 0.1 * difference)
    label = "positive" if positive_hits > negative_hits else "negative"
    return {"label": label, "score": round(confidence, 2)}


def extract_products(text: str) -> list[str]:
    normalized = clean_text(text)
    return [
        display_name
        for product_name, display_name in TOTVS_PRODUCTS.items()
        if re.search(rf"\b{re.escape(product_name)}\b", normalized)
    ]


def build_business_flags(
    intent: str,
    sentiment: dict[str, Any],
    token_count: int,
) -> dict[str, Any]:
    sentiment_label = sentiment["label"]
    return {
        "churn_signal": intent == "churn_risk" or sentiment_label == "negative",
        "price_signal": intent == "price_objection",
        "upsell_signal": intent == "upsell_opportunity",
        "satisfaction_signal": (
            intent == "satisfaction" or sentiment_label == "positive"
        ),
        "token_count": token_count,
    }


def process_text(message: dict[str, Any]) -> dict[str, Any]:
    original_text = str(message.get("text", ""))
    processed_text = clean_text(original_text)
    classification = predict_intent(processed_text)
    sentiment = analyze_sentiment(processed_text)
    products = extract_products(original_text)

    return {
        "speaker": str(message.get("speaker", "unknown")),
        "original_text": original_text,
        "processed_text": processed_text,
        "intent": classification["label"],
        "classification": classification,
        "sentiment": sentiment,
        "products": products,
        "entities": [
            {"text": product, "label": "TOTVS_PRODUCT"} for product in products
        ],
        "features": build_business_flags(
            intent=classification["label"],
            sentiment=sentiment,
            token_count=len(processed_text.split()),
        ),
    }
