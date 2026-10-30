from app.routes.api import HISTORY_LIMIT
from tests import AppTestCase, app, socket


class RoomTestCase(AppTestCase):
    """An "owner" user with a "general" room, and self.client logged in as alice (not a member)."""

    def setUp(self):
        super().setUp()
        self.owner_client = self.new_client()
        self.owner = self.register("owner", client=self.owner_client)
        self.room = self.create_room("general", client=self.owner_client)
        self.url = f"/api/rooms/{self.room['id']}"
        self.alice = self.register("alice")

    def permission(self):
        return self.client.get(f"{self.url}/permission").get_json()["permission"]


class ListRoomsTests(AppTestCase):
    def test_requires_login(self):
        self.assertError(self.client.get("/api/rooms"), 401)

    def test_empty(self):
        self.register()
        response = self.client.get("/api/rooms")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_sorted_by_name_with_permission_for_current_user(self):
        self.register("alice")
        self.create_room("zeta")
        self.create_room("alpha")
        bob = self.new_client()
        self.register("bob", client=bob)
        mid = self.create_room("mid", client=bob)

        rooms = self.client.get("/api/rooms").get_json()
        self.assertEqual(
            [(room["display_name"], room["permission"]) for room in rooms],
            [("alpha", "member"), ("mid", "none"), ("zeta", "member")],
        )
        self.assertEqual(rooms[1], {"id": mid["id"], "display_name": "mid", "permission": "none"})


class CreateRoomTests(AppTestCase):
    def test_requires_login(self):
        self.assertError(self.client.post("/api/rooms", json={"display_name": "general"}), 401)

    def test_creates_room_and_joins_creator(self):
        self.register()
        response = self.client.post("/api/rooms", json={"display_name": "  general  "})
        self.assertEqual(response.status_code, 201)
        room = response.get_json()
        self.assertEqual(room["display_name"], "general")
        self.assertEqual(room["permission"], "member")
        self.assertEqual(self.room_member_count(room["id"]), 1)
        self.assertEqual(self.client.get("/api/rooms").get_json(), [room])

    def test_rejects_duplicate_name(self):
        self.register()
        self.create_room("general")
        self.assertError(self.client.post("/api/rooms", json={"display_name": "general"}), 409)
        self.assertEqual(len(self.client.get("/api/rooms").get_json()), 1)

    def test_duplicate_check_ignores_case_and_invisible_characters(self):
        self.register()
        self.create_room("general")
        for name in ["General", "GENERAL", "gen​eral", " general\t"]:
            with self.subTest(name=name):
                self.assertError(self.client.post("/api/rooms", json={"display_name": name}), 409)
        self.assertEqual(len(self.client.get("/api/rooms").get_json()), 1)

    def test_room_name_is_sanitised(self):
        self.register()
        self.assertEqual(self.create_room("  proiect\x00 ‮ python ")["display_name"], "proiect python")

    def test_rejects_invalid_names(self):
        self.register()
        bodies = [None, {}, ["general"], {"display_name": ""}, {"display_name": "   "},
                  {"display_name": "​"}, {"display_name": 7}, {"display_name": "x" * 33}]
        for body in bodies:
            with self.subTest(body=body):
                self.assertError(self.client.post("/api/rooms", json=body), 400)
        self.assertEqual(self.client.get("/api/rooms").get_json(), [])

    def test_notifies_connected_clients(self):
        bob = self.new_client()
        self.register("bob", client=bob)
        bob_socket = socket.test_client(app, flask_test_client=bob)
        self.addCleanup(bob_socket.disconnect)
        bob_socket.get_received()

        self.register("alice")
        self.create_room("general")
        self.assertEqual([event["name"] for event in bob_socket.get_received()], ["rooms_changed"])


class JoinRoomTests(RoomTestCase):
    def test_requires_login(self):
        self.assertError(self.new_client().post(f"{self.url}/join"), 401)

    def test_unknown_room(self):
        self.assertError(self.client.post("/api/rooms/999/join"), 404)
        self.assertEqual(self.client.post("/api/rooms/abc/join").status_code, 404)

    def test_joins_room(self):
        response = self.client.post(f"{self.url}/join")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {**self.room, "permission": "member"})
        self.assertEqual(self.permission(), "member")
        self.assertEqual(self.room_member_count(self.room["id"]), 2)

    def test_joining_twice_is_a_no_op(self):
        self.client.post(f"{self.url}/join")
        response = self.client.post(f"{self.url}/join")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["permission"], "member")
        self.assertEqual(self.room_member_count(self.room["id"]), 2)

    def test_only_post_is_allowed(self):
        self.assertEqual(self.client.get(f"{self.url}/join").status_code, 405)


class LeaveRoomTests(RoomTestCase):
    def test_requires_login(self):
        self.assertError(self.new_client().post(f"{self.url}/leave"), 401)

    def test_unknown_room(self):
        self.assertError(self.client.post("/api/rooms/999/leave"), 404)

    def test_leaves_room(self):
        self.client.post(f"{self.url}/join")
        response = self.client.post(f"{self.url}/leave")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {**self.room, "permission": "none"})
        self.assertEqual(self.permission(), "none")
        self.assertEqual(self.room_member_count(self.room["id"]), 1)

    def test_leaving_when_not_a_member_is_a_no_op(self):
        response = self.client.post(f"{self.url}/leave")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["permission"], "none")
        self.assertEqual(self.room_member_count(self.room["id"]), 1)

    def test_room_survives_when_last_member_leaves(self):
        self.owner_client.post(f"{self.url}/leave")
        self.assertEqual(self.room_member_count(self.room["id"]), 0)
        self.assertEqual(self.client.get("/api/rooms").get_json(), [{**self.room, "permission": "none"}])

    def test_can_rejoin(self):
        self.client.post(f"{self.url}/join")
        self.client.post(f"{self.url}/leave")
        self.client.post(f"{self.url}/join")
        self.assertEqual(self.permission(), "member")


class RoomPermissionTests(RoomTestCase):
    def test_requires_login(self):
        self.assertError(self.new_client().get(f"{self.url}/permission"), 401)

    def test_unknown_room(self):
        self.assertError(self.client.get("/api/rooms/999/permission"), 404)

    def test_none_for_non_member(self):
        response = self.client.get(f"{self.url}/permission")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"room_id": self.room["id"], "permission": "none"})

    def test_member_for_creator(self):
        response = self.owner_client.get(f"{self.url}/permission")
        self.assertEqual(response.get_json(), {"room_id": self.room["id"], "permission": "member"})

    def test_follows_join_and_leave(self):
        self.client.post(f"{self.url}/join")
        self.assertEqual(self.permission(), "member")
        self.client.post(f"{self.url}/leave")
        self.assertEqual(self.permission(), "none")


class RoomMessagesTests(RoomTestCase):
    def messages(self, client=None):
        response = (client or self.owner_client).get(f"{self.url}/messages")
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_requires_login(self):
        self.assertError(self.new_client().get(f"{self.url}/messages"), 401)

    def test_unknown_room(self):
        self.assertError(self.client.get("/api/rooms/999/messages"), 404)

    def test_forbidden_for_non_member(self):
        self.add_messages(self.room["id"], self.owner["id"], "secret")
        self.assertError(self.client.get(f"{self.url}/messages"), 403)

    def test_empty_room(self):
        self.assertEqual(self.messages(), [])

    def test_oldest_first_with_author_name(self):
        self.client.post(f"{self.url}/join")
        self.add_messages(self.room["id"], self.owner["id"], "first")
        self.add_messages(self.room["id"], self.alice["id"], "second")

        messages = self.messages(client=self.client)
        self.assertEqual([(m["display_name"], m["content"]) for m in messages], [("owner", "first"), ("alice", "second")])
        self.assertEqual(set(messages[0]), {"id", "room_id", "display_name", "content", "sent_at"})
        self.assertEqual(messages[0]["room_id"], self.room["id"])

    def test_never_exposes_login_ids(self):
        self.add_messages(self.room["id"], self.owner["id"], "hello")
        response = self.owner_client.get(f"{self.url}/messages")
        self.assertNotIn(self.owner["id"], response.get_data(as_text=True))

    def test_only_messages_of_that_room(self):
        other = self.create_room("other", client=self.owner_client)
        self.add_messages(self.room["id"], self.owner["id"], "here")
        self.add_messages(other["id"], self.owner["id"], "elsewhere")
        self.assertEqual([m["content"] for m in self.messages()], ["here"])

    def test_limited_to_latest_messages(self):
        total = HISTORY_LIMIT + 5
        self.add_messages(self.room["id"], self.owner["id"], *(f"m{i}" for i in range(total)))
        contents = [m["content"] for m in self.messages()]
        self.assertEqual(contents, [f"m{i}" for i in range(5, total)])


class RoomIdTests(RoomTestCase):
    ROUTES = [("post", "join"), ("post", "leave"), ("get", "permission"), ("get", "messages")]

    def test_out_of_range_ids_are_not_found(self):
        for room_id in ["0", "-1", "9223372036854775808", "99999999999999999999", "1.5", "1e3"]:
            for method, route in self.ROUTES:
                with self.subTest(room_id=room_id, route=route):
                    response = getattr(self.client, method)(f"/api/rooms/{room_id}/{route}")
                    self.assertEqual(response.status_code, 404)

    def test_largest_id_is_a_normal_404(self):
        self.assertError(self.client.get("/api/rooms/9223372036854775807/permission"), 404)
