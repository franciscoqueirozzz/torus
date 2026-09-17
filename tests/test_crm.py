import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import storage
from app.api import app
from app.crm_routes import safe_csv


class CRMTests(unittest.TestCase):
    """Exercita o CRM em banco temporário, sem alterar as contas locais."""

    def setUp(self):
        self.original_db_path = storage.DB_PATH
        self.temp_directory = tempfile.TemporaryDirectory()
        storage.DB_PATH = Path(self.temp_directory.name) / "crm_test.db"
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.manager = self.headers(self.login("manager@torus.ai", "Torus@2026"))
        self.ana = self.headers(self.login("ana@torus.ai", "Vendas@2026"))
        self.carlos = self.headers(self.login("carlos@torus.ai", "Vendas@2026"))

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        storage.DB_PATH = self.original_db_path
        self.temp_directory.cleanup()

    @staticmethod
    def headers(token):
        return {"Authorization": f"Bearer {token}"}

    def login(self, email, password):
        response = self.client.post(
            "/auth/login", json={"email": email, "password": password}
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def customers(self, headers):
        return self.client.get("/customers", headers=headers).json()

    def task_payload(self, customer_id):
        return {
            "customer_id": customer_id,
            "title": "Retornar com a proposta",
            "due_date": "2026-09-10",
            "priority": "high",
        }

    def test_customer_isolation_and_duplicate(self):
        self.assertEqual(len(self.customers(self.manager)), 3)
        self.assertEqual(len(self.customers(self.ana)), 2)
        carlos_customer = self.customers(self.carlos)[0]
        self.assertEqual(
            self.client.get(
                f"/customers/{carlos_customer['id']}", headers=self.ana
            ).status_code,
            404,
        )
        payload = {"name": "Novo cliente", "seller_id": 999}
        created = self.client.post("/customers", json=payload, headers=self.ana)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(
            created.json()["seller_id"], self.customers(self.ana)[0]["seller_id"]
        )
        self.assertEqual(
            self.client.post("/customers", json=payload, headers=self.ana).status_code,
            409,
        )

    def test_customer_edit_keeps_history_and_owner(self):
        customer = self.customers(self.ana)[0]
        changed = self.client.patch(
            f"/customers/{customer['id']}",
            headers=self.ana,
            json={"name": "Nome atualizado", "stage": "renewal"},
        )
        self.assertEqual(changed.status_code, 200)
        detail = self.client.get(
            f"/customers/{customer['id']}", headers=self.ana
        ).json()
        self.assertTrue(detail["meetings"])
        self.assertTrue(
            all(
                item["customer_name"] == "Nome atualizado"
                for item in detail["meetings"]
            )
        )
        forbidden = self.client.patch(
            f"/customers/{customer['id']}", headers=self.carlos, json={"name": "Outro"}
        )
        self.assertEqual(forbidden.status_code, 404)
        reassignment = self.client.patch(
            f"/customers/{customer['id']}",
            headers=self.ana,
            json={"name": "Outro", "seller_id": 999},
        )
        self.assertEqual(reassignment.status_code, 422)

    def test_meeting_uses_existing_customer_and_seller(self):
        customer = self.customers(self.carlos)[0]
        payload = {
            "meeting_id": 1001,
            "customer_id": customer["id"],
            "customer_name": "Nome falso",
            "seller_id": 999,
            "conversation": [
                {"speaker": "cliente", "text": "Queremos expandir o Fluig."}
            ],
        }
        self.assertEqual(
            self.client.post(
                "/analyze_meeting", json=payload, headers=self.ana
            ).status_code,
            404,
        )
        response = self.client.post(
            "/analyze_meeting", json=payload, headers=self.manager
        )
        self.assertEqual(response.status_code, 200)
        record = self.client.get(
            f"/meetings/{response.json()['record_id']}", headers=self.manager
        ).json()
        self.assertEqual(record["customer_id"], customer["id"])
        self.assertEqual(record["customer_name"], customer["name"])
        self.assertEqual(record["seller"]["id"], customer["seller_id"])
        self.assertIn("score_explanation", record["summary"])

    def test_required_organizational_tables_are_synced(self):
        required = {
            "tb_cliente",
            "tb_vendedor",
            "tb_reuniao",
            "tb_transcricoes",
            "tb_tarefa",
        }
        with storage.get_connection() as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue(required.issubset(tables))
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM tb_vendedor").fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM tb_cliente").fetchone()[0],
                3,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM tb_reuniao").fetchone()[0],
                3,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM tb_transcricoes").fetchone()[
                    0
                ],
                3,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM tb_tarefa").fetchone()[0],
                0,
            )

        customer = self.customers(self.ana)[0]
        payload = {
            "meeting_id": 2201,
            "title": "Reunião organizacional",
            "customer_id": customer["id"],
            "conversation": [
                {
                    "speaker": "cliente",
                    "text": "Precisamos ampliar o Protheus no próximo mês.",
                }
            ],
        }
        response = self.client.post("/analyze_meeting", json=payload, headers=self.ana)
        self.assertEqual(response.status_code, 200)
        record_id = response.json()["record_id"]

        with storage.get_connection() as connection:
            organized = connection.execute(
                """SELECT r.*,t.texto_completo,t.sentimento_geral
                   FROM tb_reuniao r JOIN tb_transcricoes t
                     ON t.tb_reuniao_id_reuniao=r.id_reuniao
                   WHERE r.id_reuniao=?""",
                (str(record_id),),
            ).fetchone()
            self.assertIsNotNone(organized)
            self.assertEqual(organized["titulo_reuniao"], payload["title"])
            self.assertEqual(organized["tb_cliente_id_cliente"], str(customer["id"]))
            self.assertEqual(
                organized["tb_vendedor_id_vendedor"], str(customer["seller_id"])
            )
            self.assertIn("ampliar o Protheus", organized["texto_completo"])
            self.assertGreaterEqual(organized["sentimento_geral"], 0)
            self.assertLessEqual(organized["sentimento_geral"], 1)

        renamed = self.client.patch(
            f"/meetings/{record_id}",
            json={"title": "Título sincronizado"},
            headers=self.ana,
        )
        self.assertEqual(renamed.status_code, 200)
        with storage.get_connection() as connection:
            title = connection.execute(
                "SELECT titulo_reuniao FROM tb_reuniao WHERE id_reuniao=?",
                (str(record_id),),
            ).fetchone()[0]
        self.assertEqual(title, "Título sincronizado")

    def test_task_create_edit_complete_and_isolation(self):
        customer = self.customers(self.ana)[0]
        payload = self.task_payload(customer["id"])
        self.assertEqual(
            self.client.post("/tasks", json=payload, headers=self.carlos).status_code,
            404,
        )
        response = self.client.post("/tasks", json=payload, headers=self.ana)
        self.assertEqual(response.status_code, 201)
        task = response.json()
        with storage.get_connection() as connection:
            organized = connection.execute(
                "SELECT * FROM tb_tarefa WHERE id_tarefa=?", (str(task["id"]),)
            ).fetchone()
        self.assertIsNotNone(organized)
        self.assertEqual(organized["titulo_tarefa"], payload["title"])
        self.assertEqual(organized["prioridade_tarefa"], "Alta")
        self.assertEqual(organized["status_tarefa"], "Pendente")
        self.assertEqual(organized["tb_cliente_id_cliente"], str(customer["id"]))
        self.assertEqual(
            organized["tb_vendedor_id_vendedor"], str(customer["seller_id"])
        )
        self.assertIsNone(organized["tb_reuniao_id_reuniao"])
        self.assertEqual(self.client.get("/tasks", headers=self.carlos).json(), [])
        update = {key: task[key] for key in ("title", "due_date", "priority", "notes")}
        update["status"] = "done"
        self.assertEqual(
            self.client.patch(
                f"/tasks/{task['id']}", json=update, headers=self.carlos
            ).status_code,
            404,
        )
        done = self.client.patch(
            f"/tasks/{task['id']}", json=update, headers=self.ana
        ).json()
        self.assertIsNotNone(done["completed_at"])
        with storage.get_connection() as connection:
            organized_done = connection.execute(
                """SELECT status_tarefa,data_conclusao FROM tb_tarefa
                   WHERE id_tarefa=?""",
                (str(task["id"]),),
            ).fetchone()
        self.assertEqual(organized_done["status_tarefa"], "Concluída")
        self.assertIsNotNone(organized_done["data_conclusao"])
        update["status"] = "open"
        reopened = self.client.patch(
            f"/tasks/{task['id']}", json=update, headers=self.manager
        ).json()
        self.assertIsNone(reopened["completed_at"])
        with storage.get_connection() as connection:
            organized_reopened = connection.execute(
                """SELECT status_tarefa,data_conclusao FROM tb_tarefa
                   WHERE id_tarefa=?""",
                (str(task["id"]),),
            ).fetchone()
        self.assertEqual(organized_reopened["status_tarefa"], "Pendente")
        self.assertIsNone(organized_reopened["data_conclusao"])

    def test_task_cannot_reference_other_customers_meeting(self):
        customers = self.customers(self.ana)
        other = self.client.get(
            f"/customers/{customers[1]['id']}", headers=self.ana
        ).json()
        payload = self.task_payload(customers[0]["id"])
        payload["meeting_id"] = other["meetings"][0]["id"]
        self.assertEqual(
            self.client.post("/tasks", json=payload, headers=self.ana).status_code, 422
        )
        payload["meeting_id"] = None
        payload["due_date"] = "não é uma data"
        self.assertEqual(
            self.client.post("/tasks", json=payload, headers=self.ana).status_code, 422
        )

    def test_account_creation_requires_manager_and_password(self):
        payload = {
            "name": "Teste",
            "email": "teste@example.com",
            "role": "seller",
            "password": "Uma frase de teste longa",
            "current_password": "Torus@2026",
        }
        self.assertEqual(
            self.client.post("/users", json=payload, headers=self.ana).status_code, 403
        )
        invalid = {**payload, "current_password": "errada"}
        self.assertEqual(
            self.client.post("/users", json=invalid, headers=self.manager).status_code,
            400,
        )
        response = self.client.post("/users", json=payload, headers=self.manager)
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.text)
        self.assertEqual(
            self.client.post("/users", json=payload, headers=self.manager).status_code,
            409,
        )
        token = self.login(payload["email"], payload["password"])
        self.assertEqual(
            self.client.get("/customers", headers=self.headers(token)).json(), []
        )

    def test_deactivation_revokes_sessions_and_preserves_records(self):
        seller_id = self.customers(self.ana)[0]["seller_id"]
        payload = {"active": False, "current_password": "Torus@2026"}
        response = self.client.patch(
            f"/users/{seller_id}/access", json=payload, headers=self.manager
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/auth/me", headers=self.ana).status_code, 401)
        self.assertEqual(len(self.customers(self.manager)), 3)
        self.assertEqual(
            len(self.client.get("/meetings", headers=self.manager).json()), 3
        )
        storage.init_db()
        self.assertIsNone(storage.authenticate_user("ana@torus.ai", "Vendas@2026"))
        me = self.client.get("/auth/me", headers=self.manager).json()
        self.assertEqual(
            self.client.patch(
                f"/users/{me['id']}/access", json=payload, headers=self.manager
            ).status_code,
            422,
        )

    def test_password_change_preserves_spaces_and_revokes_all_sessions(self):
        new_password = "  Uma frase com espaços  "
        payload = {"current_password": "errada", "new_password": new_password}
        self.assertEqual(
            self.client.post(
                "/auth/change-password", json=payload, headers=self.ana
            ).status_code,
            400,
        )
        payload["current_password"] = "Vendas@2026"
        response = self.client.post(
            "/auth/change-password", json=payload, headers=self.ana
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/auth/me", headers=self.ana).status_code, 401)
        self.assertIsNone(storage.authenticate_user("ana@torus.ai", "Vendas@2026"))
        self.login("ana@torus.ai", new_password)

    def test_migration_is_idempotent(self):
        before = self.customers(self.manager)
        storage.init_db()
        storage.init_db()
        self.assertEqual(self.customers(self.manager), before)
        self.assertEqual(
            len(self.client.get("/meetings", headers=self.manager).json()), 3
        )

    def test_csv_is_scoped_and_formula_safe(self):
        response = self.client.get("/reports/meetings.csv", headers=self.ana)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Carlos Lima", response.text)
        self.assertIn("Ana Souza", response.text)
        self.assertTrue(safe_csv("=SUM(1,2)").startswith("'"))
        self.assertTrue(safe_csv("  @formula").startswith("'"))
        self.assertEqual(safe_csv("Cliente comum"), "Cliente comum")

    def test_malformed_upload_is_rejected(self):
        for payload in ([], "text", 12, None):
            response = self.client.post(
                "/analyze_meeting_file",
                headers=self.ana,
                files={
                    "file": (
                        "meeting.json",
                        json.dumps(payload).encode(),
                        "application/json",
                    )
                },
            )
            self.assertEqual(response.status_code, 400)

    def test_frontend_assets_and_patch_preflight(self):
        self.assertEqual(self.client.get("/assets/app.js").status_code, 200)
        self.assertEqual(self.client.get("/assets/styles.css").status_code, 200)
        response = self.client.options(
            "/customers/1",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
