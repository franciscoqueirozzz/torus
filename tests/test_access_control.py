import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import storage
from app.api import app


class AuthAccessTests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = storage.DB_PATH
        self.temp_directory = tempfile.TemporaryDirectory()
        storage.DB_PATH = Path(self.temp_directory.name) / "test_meetings.db"
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        storage.DB_PATH = self.original_db_path
        self.temp_directory.cleanup()

    def login(self, email, password):
        response = self.client.post(
            "/auth/login", json={"email": email, "password": password}
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    @staticmethod
    def headers(token):
        return {"Authorization": f"Bearer {token}"}

    def test_invalid_login_uses_generic_message(self):
        response = self.client.post(
            "/auth/login", json={"email": "missing@torus.ai", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "E-mail ou senha incorretos.")

    def test_seller_only_sees_assigned_meetings(self):
        manager_token = self.login("manager@torus.ai", "Torus@2026")
        ana_token = self.login("ana@torus.ai", "Vendas@2026")
        manager_meetings = self.client.get(
            "/meetings", headers=self.headers(manager_token)
        ).json()
        ana_meetings = self.client.get(
            "/meetings", headers=self.headers(ana_token)
        ).json()
        self.assertEqual(len(manager_meetings), 3)
        self.assertEqual(len(ana_meetings), 2)
        self.assertTrue(
            all(item["seller"]["name"] == "Ana Souza" for item in ana_meetings)
        )

        carlos_meeting = next(
            item for item in manager_meetings if item["seller"]["name"] == "Carlos Lima"
        )
        forbidden = self.client.get(
            f"/meetings/{carlos_meeting['id']}", headers=self.headers(ana_token)
        )
        self.assertEqual(forbidden.status_code, 404)

    def test_manager_sees_team_and_can_assign_meeting(self):
        manager_token = self.login("manager@torus.ai", "Torus@2026")
        sellers = self.client.get(
            "/users/sellers", headers=self.headers(manager_token)
        ).json()
        carlos = next(item for item in sellers if item["name"] == "Carlos Lima")
        payload = {
            "meeting_id": 901,
            "title": "Expansão de conta",
            "customer_name": "Cliente Teste",
            "seller_id": carlos["id"],
            "conversation": [
                {"speaker": "cliente", "text": "Queremos ampliar as licenças do Fluig."}
            ],
        }
        response = self.client.post(
            "/analyze_meeting", json=payload, headers=self.headers(manager_token)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["seller"]["name"], "Carlos Lima")

    def test_seller_cannot_assign_meeting_to_another_user(self):
        ana_token = self.login("ana@torus.ai", "Vendas@2026")
        payload = {
            "meeting_id": 902,
            "title": "Reunião da Ana",
            "customer_name": "Cliente Teste",
            "seller_id": 999,
            "conversation": [
                {"speaker": "cliente", "text": "Estamos satisfeitos com o Protheus."}
            ],
        }
        response = self.client.post(
            "/analyze_meeting", json=payload, headers=self.headers(ana_token)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["seller"]["name"], "Ana Souza")

    def test_logout_invalidates_session(self):
        token = self.login("ana@torus.ai", "Vendas@2026")
        self.assertEqual(
            self.client.post("/auth/logout", headers=self.headers(token)).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/auth/me", headers=self.headers(token)).status_code, 401
        )

    def test_dashboard_and_health_are_available(self):
        dashboard = self.client.get("/")
        health = self.client.get("/health")

        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Torus", dashboard.text)
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

    def test_local_frontend_preflight_is_accepted(self):
        response = self.client.options(
            "/auth/login",
            headers={
                "Origin": "null",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "null")

    def test_health_rejects_missing_or_unreadable_model(self):
        with patch("app.api.load_model", return_value=None):
            self.assertEqual(self.client.get("/health").status_code, 503)
        with patch("app.api.load_model", side_effect=ValueError("invalid JSON")):
            self.assertEqual(self.client.get("/health").status_code, 503)

    def test_model_metadata_requires_login(self):
        self.assertEqual(self.client.get("/model_metrics").status_code, 401)
        token = self.login("ana@torus.ai", "Vendas@2026")
        response = self.client.get("/model_metrics", headers=self.headers(token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model_type"], "logistic_regression")
        self.assertIn("evaluation_summary", response.json())
        self.assertNotIn("models", response.json())

    def test_empty_meeting_is_rejected(self):
        token = self.login("ana@torus.ai", "Vendas@2026")
        response = self.client.post(
            "/analyze_meeting",
            json={"meeting_id": 903, "conversation": []},
            headers=self.headers(token),
        )

        self.assertEqual(response.status_code, 422)

    def test_oversized_file_is_rejected(self):
        token = self.login("ana@torus.ai", "Vendas@2026")
        response = self.client.post(
            "/analyze_meeting_file",
            files={"file": ("meeting.json", b" " * 1_000_001, "application/json")},
            headers=self.headers(token),
        )

        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
