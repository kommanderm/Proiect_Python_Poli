from app.socket.socket import MESSAGE_MAX_LENGTH
from tests import AppTestCase, Message, app, db, socket


def received_messages(sio):
    return [event["args"] for event in sio.get_received() if event["name"] == "message"]


class SocketTestCase(AppTestCase):
    """alice (self.client) created "general" and has a connected socket that hasn't entered a room."""

    def setUp(self):
        super().setUp()
        self.alice = self.register("alice")
        self.room = self.create_room("general")
        self.alice_socket = self.connect(self.client)

    def connect(self, client):
        sio = socket.test_client(app, flask_test_client=client)
        self.addCleanup(self.disconnect, sio)
        return sio

    @staticmethod
    def disconnect(sio):
        if sio.is_connected():
            sio.disconnect()

    def member(self, display_name, room=None):
        """A new user who joined `room` (default: general), with a connected socket."""
        client = self.new_client()
        self.register(display_name, client=client)
        client.post(f"/api/rooms/{(room or self.room)['id']}/join")
        return client, self.connect(client)

    def outsider(self, display_name):
        """A new user who is in no rooms, with a connected socket."""
        client = self.new_client()
        self.register(display_name, client=client)
        return self.connect(client)

    def enter(self, sio, room=None):
        reply = sio.emit("enter_room", {"room_id": (room or self.room)["id"]}, callback=True)
        self.assertEqual(reply, {"ok": True})

    def send(self, sio, content, room=None):
        return sio.emit("send_message", {"room_id": (room or self.room)["id"], "content": content}, callback=True)

    def stored(self):
        with app.app_context():
            return db.session.scalars(db.select(Message.content).order_by(Message.id)).all()

    def assertRefused(self, reply):
        self.assertIs(reply["ok"], False)
        self.assertIsInstance(reply["error"], str)


class ConnectTests(AppTestCase):
    def test_refused_when_logged_out(self):
        self.assertFalse(socket.test_client(app, flask_test_client=self.client).is_connected())

    def test_refused_for_unknown_user(self):
        with self.client.session_transaction() as session:
            session["user_id"] = "000000000000"
        self.assertFalse(socket.test_client(app, flask_test_client=self.client).is_connected())

    def test_accepted_when_logged_in(self):
        self.register()
        sio = socket.test_client(app, flask_test_client=self.client)
        self.addCleanup(sio.disconnect)
        self.assertTrue(sio.is_connected())


class EnterRoomTests(SocketTestCase):
    def test_member_can_enter(self):
        self.enter(self.alice_socket)

    def test_non_member_is_refused(self):
        bob_socket = self.outsider("bob")
        self.assertRefused(bob_socket.emit("enter_room", {"room_id": self.room["id"]}, callback=True))
        self.send(self.alice_socket, "hi")
        self.assertEqual(received_messages(bob_socket), [])

    def test_rejects_bad_payloads(self):
        room_id = self.room["id"]
        for data in [None, {}, {"room_id": None}, {"room_id": str(room_id)}, {"room_id": 999}, "general", [room_id]]:
            with self.subTest(data=data):
                self.assertRefused(self.alice_socket.emit("enter_room", data, callback=True))

    def test_messages_arrive_only_after_entering(self):
        _, bob_socket = self.member("bob")
        self.send(self.alice_socket, "before")
        self.assertEqual(received_messages(bob_socket), [])

        self.enter(bob_socket)
        self.send(self.alice_socket, "after")
        self.assertEqual([m["content"] for m in received_messages(bob_socket)], ["after"])

    def test_entering_a_room_leaves_the_previous_one(self):
        other = self.create_room("other")
        bob_client, bob_socket = self.member("bob")
        bob_client.post(f"/api/rooms/{other['id']}/join")
        self.enter(bob_socket)
        self.enter(bob_socket, room=other)

        self.send(self.alice_socket, "in general")
        self.send(self.alice_socket, "in other", room=other)
        self.assertEqual([m["content"] for m in received_messages(bob_socket)], ["in other"])


class ExitRoomTests(SocketTestCase):
    def test_stops_messages(self):
        _, bob_socket = self.member("bob")
        self.enter(bob_socket)
        self.assertEqual(bob_socket.emit("exit_room", {}, callback=True), {"ok": True})
        self.send(self.alice_socket, "hi")
        self.assertEqual(received_messages(bob_socket), [])

    def test_works_without_payload_or_room(self):
        self.assertEqual(self.alice_socket.emit("exit_room", callback=True), {"ok": True})


class SendMessageTests(SocketTestCase):
    def test_broadcasts_to_everyone_in_the_room_including_sender(self):
        _, bob_socket = self.member("bob")
        self.enter(self.alice_socket)
        self.enter(bob_socket)
        self.assertEqual(self.send(self.alice_socket, "hello"), {"ok": True})

        [to_alice] = received_messages(self.alice_socket)
        [to_bob] = received_messages(bob_socket)
        self.assertEqual(to_alice, to_bob)
        self.assertEqual(set(to_bob), {"id", "room_id", "display_name", "content", "sent_at"})
        self.assertEqual(
            (to_bob["room_id"], to_bob["display_name"], to_bob["content"]),
            (self.room["id"], "alice", "hello"),
        )

    def test_broadcast_matches_stored_history(self):
        self.enter(self.alice_socket)
        self.send(self.alice_socket, "hello")
        [message] = received_messages(self.alice_socket)
        history = self.client.get(f"/api/rooms/{self.room['id']}/messages").get_json()
        self.assertEqual(history, [message])

    def test_content_is_trimmed(self):
        self.send(self.alice_socket, "  hi  ")
        self.assertEqual(self.stored(), ["hi"])

    def test_accepts_max_length(self):
        self.assertEqual(self.send(self.alice_socket, "x" * MESSAGE_MAX_LENGTH), {"ok": True})

    def test_rejects_too_long(self):
        self.assertRefused(self.send(self.alice_socket, "x" * (MESSAGE_MAX_LENGTH + 1)))
        self.assertEqual(self.stored(), [])

    def test_rejects_invalid_content(self):
        self.enter(self.alice_socket)
        for content in [None, "", "   ", 42, ["hi"]]:
            with self.subTest(content=content):
                self.assertRefused(self.send(self.alice_socket, content))
        self.assertRefused(self.alice_socket.emit("send_message", {"room_id": self.room["id"]}, callback=True))
        self.assertEqual(self.stored(), [])
        self.assertEqual(received_messages(self.alice_socket), [])

    def test_rejects_bad_payloads(self):
        for data in [None, {}, "hi", {"content": "hi"}, {"room_id": 999, "content": "hi"}]:
            with self.subTest(data=data):
                self.assertRefused(self.alice_socket.emit("send_message", data, callback=True))
        self.assertEqual(self.stored(), [])

    def test_non_member_cannot_send(self):
        self.assertRefused(self.send(self.outsider("bob"), "hi"))
        self.assertEqual(self.stored(), [])

    def test_not_delivered_to_other_rooms(self):
        other = self.create_room("other")
        _, bob_socket = self.member("bob", room=other)
        self.enter(bob_socket, room=other)
        self.send(self.alice_socket, "hi")
        self.assertEqual(received_messages(bob_socket), [])

    def test_member_can_send_without_entering(self):
        _, bob_socket = self.member("bob")
        self.enter(self.alice_socket)
        self.assertEqual(self.send(bob_socket, "hi"), {"ok": True})
        self.assertEqual([m["content"] for m in received_messages(self.alice_socket)], ["hi"])
        self.assertEqual(received_messages(bob_socket), [])

    def test_never_exposes_login_ids(self):
        self.enter(self.alice_socket)
        self.send(self.alice_socket, "hi")
        [message] = received_messages(self.alice_socket)
        self.assertNotIn(self.alice["id"], str(message))

    def test_leaving_over_http_revokes_sending_at_once(self):
        bob_client, bob_socket = self.member("bob")
        bob_client.post(f"/api/rooms/{self.room['id']}/leave")
        self.assertRefused(self.send(bob_socket, "hi"))

    def test_socket_that_left_keeps_receiving_until_exit_room(self):
        # the frontend closes this gap by checking /permission for every received message
        bob_client, bob_socket = self.member("bob")
        self.enter(bob_socket)
        bob_client.post(f"/api/rooms/{self.room['id']}/leave")

        self.send(self.alice_socket, "one")
        self.assertEqual(len(received_messages(bob_socket)), 1)
        permission = bob_client.get(f"/api/rooms/{self.room['id']}/permission").get_json()
        self.assertEqual(permission["permission"], "none")

        bob_socket.emit("exit_room", {}, callback=True)
        self.send(self.alice_socket, "two")
        self.assertEqual(received_messages(bob_socket), [])
