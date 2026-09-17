import hashlib
import json
import unittest
from pathlib import Path

from app.intent_classifier import (
    MODEL_PATH,
    get_model_metadata,
    load_model,
    predict_intent,
)
from app.meeting_analysis import analyze_meeting
from app.text_processing import process_text

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def test_runtime_model_matches_metadata(self):
        metadata = get_model_metadata()
        model = load_model()

        self.assertIsNotNone(model)
        self.assertEqual(model["model_type"], metadata["model_type"])
        self.assertEqual(model["labels"], metadata["labels"])
        self.assertEqual(
            hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(), metadata["sha256"]
        )

    def test_examples_from_each_class(self):
        examples = {
            "Pretendemos cancelar o contrato no próximo mês": "churn_risk",
            "O valor está muito alto para nosso orçamento": "price_objection",
            "Queremos expandir o Fluig para outras filiais": "upsell_opportunity",
            "Estamos muito satisfeitos com o atendimento": "satisfaction",
            "A reunião foi marcada para segunda-feira": "neutral",
        }

        for text, expected_label in examples.items():
            with self.subTest(text=text):
                self.assertEqual(predict_intent(text)["label"], expected_label)

    def test_product_and_model_are_reported(self):
        result = process_text(
            {"speaker": "cliente", "text": "Queremos expandir o Fluig."}
        )

        self.assertIn("Fluig", result["products"])
        self.assertEqual(result["classification"]["model"], "logistic_regression")
        self.assertGreater(result["classification"]["confidence"], 0)

    def test_meeting_has_scores_and_a_recommendation(self):
        meeting = json.loads(
            (BACKEND_ROOT / "examples" / "sample_meeting.json").read_text(
                encoding="utf-8"
            )
        )
        result = analyze_meeting(meeting)
        summary = result["summary"]

        expected_fields = {
            "churn_risk_score",
            "opportunity_score",
            "products_identified",
            "key_terms",
            "recommended_action",
        }
        self.assertTrue(expected_fields.issubset(summary))
        self.assertGreaterEqual(summary["churn_risk_score"], 0)
        self.assertLessEqual(summary["churn_risk_score"], 100)
        self.assertGreaterEqual(summary["opportunity_score"], 0)
        self.assertLessEqual(summary["opportunity_score"], 100)


if __name__ == "__main__":
    unittest.main()
