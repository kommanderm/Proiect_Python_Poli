from datetime import datetime, timedelta, timezone
from unittest import mock

from tests import AppTestCase


class RegisterTests(AppTestCase):
    def test_creates_user_and_logs_in(self):
        response = self.client.post("/api/register", json={"display_name": "  alice  "})
        self.assertEqual(response.status_code, 201)
        user = response.get_json()
        self.assertEqual(user["display_name"], "alice")
        self.assertRegex(user["id"], r"^[0-9a-f]{12}$")
        self.assertEqual(datetime.fromisoformat(user["registered_at"]).utcoffset(), timedelta(0))
        self.assertEqual(self.client.get("/api/me").get_json(), user)

    def test_session_lasts_seven_days(self):
        self.register()
        expires = self.client.get_cookie("session").expires
        self.assertIsNotNone(expires)
        remaining = expires - datetime.now(timezone.utc)
        self.assertTrue(timedelta(days=6, hours=23) < remaining <= timedelta(days=7), remaining)

    def test_accepts_32_character_name(self):
        self.assertEqual(self.register("x" * 32)["display_name"], "x" * 32)

    def test_rejects_invalid_display_names(self):
        bodies = [None, {}, ["alice"], {"display_name": ""}, {"display_name": "   "},
                  {"display_name": "x" * 33}, {"display_name": 42}]
        for body in bodies:
            with self.subTest(body=body):
                self.assertError(self.client.post("/api/register", json=body), 400)
        self.assertError(self.client.post("/api/register", data={"display_name": "alice"}), 400)
        self.assertError(self.client.get("/api/me"), 401)

    def test_display_names_need_not_be_unique(self):
        first = self.register("alice", client=self.new_client())
        second = self.register("alice")
        self.assertNotEqual(first["id"], second["id"])

    def test_retries_when_generated_id_is_taken(self):
        taken = self.register("alice", client=self.new_client())["id"]
        with mock.patch("secrets.token_hex", side_effect=[taken, "0123456789ab"]):
            user = self.register("bob")
        self.assertEqual(user["id"], "0123456789ab")

    def test_replaces_current_session(self):
        self.register("alice")
        bob = self.register("bob")
        self.assertEqual(self.client.get("/api/me").get_json()["id"], bob["id"])


class LoginTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.alice = self.register("alice", client=self.new_client())

    def test_logs_in_with_id(self):
        response = self.client.post("/api/login", json={"id": self.alice["id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), self.alice)
        self.assertEqual(self.client.get("/api/me").get_json(), self.alice)

    def test_id_is_trimmed_and_case_insensitive(self):
        response = self.client.post("/api/login", json={"id": f"  {self.alice['id'].upper()}  "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["id"], self.alice["id"])

    def test_rejects_unknown_or_missing_id(self):
        for body in [None, {}, {"id": ""}, {"id": 123}, {"id": "000000000000"}]:
            with self.subTest(body=body):
                self.assertError(self.client.post("/api/login", json=body), 401)
        self.assertError(self.client.get("/api/me"), 401)

    def test_failed_login_keeps_current_session(self):
        bob = self.register("bob")
        self.assertError(self.client.post("/api/login", json={"id": "000000000000"}), 401)
        self.assertEqual(self.client.get("/api/me").get_json()["id"], bob["id"])

    def test_switches_user(self):
        self.register("bob")
        self.client.post("/api/login", json={"id": self.alice["id"]})
        self.assertEqual(self.client.get("/api/me").get_json()["id"], self.alice["id"])


class LogoutTests(AppTestCase):
    def test_logs_out(self):
        self.register()
        response = self.client.post("/api/logout")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.data, b"")
        self.assertError(self.client.get("/api/me"), 401)

    def test_logout_when_logged_out(self):
        self.assertEqual(self.client.post("/api/logout").status_code, 204)

    def test_can_log_back_in_with_same_id(self):
        user = self.register()
        self.client.post("/api/logout")
        self.client.post("/api/login", json={"id": user["id"]})
        self.assertEqual(self.client.get("/api/me").get_json(), user)


class MeTests(AppTestCase):
    def test_requires_login(self):
        self.assertError(self.client.get("/api/me"), 401)

    def test_returns_current_user(self):
        user = self.register()
        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), user)

    def test_session_for_deleted_user_is_rejected(self):
        with self.client.session_transaction() as session:
            session["user_id"] = "000000000000"
        self.assertError(self.client.get("/api/me"), 401)
