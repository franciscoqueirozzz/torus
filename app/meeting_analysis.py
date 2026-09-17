"""Consolida as falas em indicadores da reunião e uma próxima ação."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.text_processing import process_text

STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "essa",
    "esse",
    "esta",
    "este",
    "eu",
    "mais",
    "nao",
    "não",
    "no",
    "nos",
    "nossa",
    "nosso",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "que",
    "se",
    "sem",
    "um",
    "uma",
    "vamos",
    "voce",
    "você",
    "voces",
    "vocês",
}

# Estes pesos são hipóteses de negócio para o protótipo, não parâmetros aprendidos.
CHURN_CONFIDENCE_WEIGHT = 45
PRICE_OBJECTION_WEIGHT = 12
NEGATIVE_SENTIMENT_WEIGHT = 80
UPSELL_CONFIDENCE_WEIGHT = 45
PRODUCT_MENTION_WEIGHT = 8


def _sentiment_value(sentiment: dict[str, Any]) -> float:
    label = sentiment.get("label", "neutral")
    confidence = float(sentiment.get("score", 0.5))
    if label == "positive":
        return 0.5 + confidence / 2
    if label == "negative":
        return 0.5 - confidence / 2
    return 0.5


def _speech_share(conversation: list[dict[str, Any]]) -> dict[str, float]:
    words_by_speaker: Counter[str] = Counter()
    for message in conversation:
        speaker = str(message.get("speaker", "unknown")).lower()
        words_by_speaker[speaker] += len(str(message.get("text", "")).split())

    total_words = sum(words_by_speaker.values())
    if not total_words:
        return {"cliente": 0.0, "vendedor": 0.0}
    return {
        "cliente": round(words_by_speaker["cliente"] / total_words, 2),
        "vendedor": round(words_by_speaker["vendedor"] / total_words, 2),
    }


def _key_terms(
    conversation: list[dict[str, Any]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    words = []
    for message in conversation:
        words.extend(
            word
            for word in re.findall(
                r"[a-zA-ZÀ-ÿ]{3,}",
                str(message.get("text", "")).lower(),
            )
            if word not in STOPWORDS
        )
    return [
        {"term": term, "count": count}
        for term, count in Counter(words).most_common(limit)
    ]


def _recommended_action(
    churn_score: float,
    opportunity_score: float,
    objections: list[str],
) -> str:
    if churn_score >= 70:
        return "Abrir um plano de retenção e marcar contato executivo em até 24 horas."
    if objections and churn_score >= 40:
        return "Rever a proposta de valor e as condições antes do próximo contato."
    if opportunity_score >= 45:
        return "Preparar uma proposta de expansão alinhada aos módulos citados."
    if churn_score >= 30:
        return (
            "Fazer um follow-up para entender a insatisfação e combinar responsáveis."
        )
    return "Registrar os próximos passos e manter o acompanhamento normal."


def analyze_meeting(meeting: dict[str, Any]) -> dict[str, Any]:
    conversation = meeting.get("conversation", [])
    message_results = [process_text(message) for message in conversation]

    customer_sentiments = []
    churn_confidences = []
    upsell_confidences = []
    objections = []
    products: set[str] = set()

    for result in message_results:
        products.update(result["products"])
        if result["speaker"].lower() != "cliente":
            continue

        customer_sentiments.append(_sentiment_value(result["sentiment"]))
        confidence = float(result["classification"]["confidence"])
        if result["intent"] == "churn_risk":
            churn_confidences.append(confidence)
        elif result["intent"] == "upsell_opportunity":
            upsell_confidences.append(confidence)
        elif result["intent"] == "price_objection":
            objections.append(result["original_text"])

    average_sentiment = (
        sum(customer_sentiments) / len(customer_sentiments)
        if customer_sentiments
        else 0.5
    )
    negative_sentiment = max(0.0, 0.5 - average_sentiment)

    churn_score = min(
        100.0,
        sum(churn_confidences) * CHURN_CONFIDENCE_WEIGHT
        + len(objections) * PRICE_OBJECTION_WEIGHT
        + negative_sentiment * NEGATIVE_SENTIMENT_WEIGHT,
    )
    opportunity_score = min(
        100.0,
        sum(upsell_confidences) * UPSELL_CONFIDENCE_WEIGHT
        + len(products) * PRODUCT_MENTION_WEIGHT,
    )

    churn_score = round(churn_score, 2)
    opportunity_score = round(opportunity_score, 2)
    sentiment_score = round(average_sentiment * 100, 2)

    return {
        "meeting_id": meeting.get("meeting_id"),
        "summary": {
            "score_explanation": {
                "churn": {
                    "intent_points": round(
                        sum(churn_confidences) * CHURN_CONFIDENCE_WEIGHT, 2
                    ),
                    "price_points": len(objections) * PRICE_OBJECTION_WEIGHT,
                    "sentiment_points": round(
                        negative_sentiment * NEGATIVE_SENTIMENT_WEIGHT, 2
                    ),
                },
                "opportunity": {
                    "intent_points": round(
                        sum(upsell_confidences) * UPSELL_CONFIDENCE_WEIGHT, 2
                    ),
                    "product_points": len(products) * PRODUCT_MENTION_WEIGHT,
                },
                "customer_speeches": len(customer_sentiments),
                "limit": 100,
                "note": (
                    "Os pontos seguem regras fixas e não são probabilidades. "
                    "Produtos de qualquer participante contam para oportunidade."
                ),
            },
            "average_customer_sentiment": round(average_sentiment, 2),
            "sentiment_score": sentiment_score,
            "churn_signals": len(churn_confidences),
            "upsell_opportunities": len(upsell_confidences),
            "objections": objections,
            "products_identified": sorted(products),
            "key_terms": _key_terms(conversation),
            "speech_ratio": _speech_share(conversation),
            "churn_risk_score": churn_score,
            "opportunity_score": opportunity_score,
            "recommended_action": _recommended_action(
                churn_score,
                opportunity_score,
                objections,
            ),
            "model_used": (
                message_results[0]["classification"]["model"]
                if message_results
                else "not_available"
            ),
        },
        "message_analysis": message_results,
    }
