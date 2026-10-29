// Mirrors app.db.Permission
const Permission = Object.freeze({ NONE: "none", MEMBER: "member" });

const roomLists = {
  [Permission.MEMBER]: document.getElementById("rooms-member"),
  [Permission.NONE]: document.getElementById("rooms-none"),
};
const roomTitle = document.getElementById("room-title");
const messageList = document.getElementById("messages");
const messageForm = document.getElementById("message-form");
const createRoomForm = document.getElementById("create-room-form");
const errorBox = document.getElementById("error");

const socket = io(ORIGIN);

let activeRoom = null;
const shown = new Set(); // ids of messages already rendered for activeRoom

// Room changes and incoming messages are handled one at a time, in arrival order.
let queue = Promise.resolve();
function enqueue(task) {
  queue = queue.then(task).catch((error) => {
    errorBox.textContent = error.message;
  });
}

function emitAck(event, data) {
  return new Promise((resolve, reject) => {
    socket.emit(event, data, (reply) => (reply.ok ? resolve(reply) : reject(new Error(reply.error))));
  });
}

function roomItem(room) {
  const item = document.createElement("li");
  item.classList.add(`perm-${room.permission}`);
  item.classList.toggle("active", room.id === activeRoom?.id);

  const isMember = room.permission === Permission.MEMBER;
  const name = document.createElement(isMember ? "button" : "span");
  name.className = "room-name";
  name.textContent = room.display_name;

  const action = document.createElement("button");
  if (isMember) {
    name.onclick = () => enqueue(() => openRoom(room));
    action.textContent = "Leave";
    action.onclick = () => enqueue(() => leaveRoom(room));
  } else {
    action.textContent = "Join";
    action.onclick = () => enqueue(() => joinRoom(room));
  }

  item.append(name, action);
  return item;
}

async function loadRooms() {
  const rooms = await api("/api/rooms");
  for (const list of Object.values(roomLists)) list.replaceChildren();
  for (const room of rooms) roomLists[room.permission]?.append(roomItem(room));
}

function renderMessage(message) {
  if (shown.has(message.id)) return;
  shown.add(message.id);

  const item = document.createElement("li");
  const time = document.createElement("time");
  time.dateTime = message.sent_at;
  time.textContent = new Date(message.sent_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const author = document.createElement("strong");
  author.textContent = message.display_name;
  const content = document.createElement("span");
  content.textContent = message.content;

  item.append(time, " ", author, " ", content);
  messageList.append(item);
  messageList.scrollTop = messageList.scrollHeight;
}

async function openRoom(room) {
  await emitAck("enter_room", { room_id: room.id });
  activeRoom = room;
  shown.clear();
  messageList.replaceChildren();
  roomTitle.textContent = room.display_name;
  messageForm.hidden = false;
  const history = await api(`/api/rooms/${room.id}/messages`);
  history.forEach(renderMessage);
  await loadRooms();
}

async function closeRoom() {
  await emitAck("exit_room", {});
  activeRoom = null;
  shown.clear();
  messageList.replaceChildren();
  roomTitle.textContent = "Pick a room";
  messageForm.hidden = true;
}

async function joinRoom(room) {
  await openRoom(await api(`/api/rooms/${room.id}/join`, { method: "POST" }));
}

async function leaveRoom(room) {
  await api(`/api/rooms/${room.id}/leave`, { method: "POST" });
  if (room.id === activeRoom?.id) await closeRoom();
  await loadRooms();
}

socket.on("connect", () => {
  errorBox.textContent = "";
  // a fresh connection is in no socket rooms, and may have missed messages
  if (activeRoom) enqueue(() => openRoom(activeRoom));
});

socket.on("connect_error", () => {
  // inactive means the server refused us (session gone), not a network blip
  if (!socket.active) location.href = "/";
  else errorBox.textContent = "Connection lost, retrying…";
});

socket.on("message", (message) =>
  enqueue(async () => {
    if (message.room_id !== activeRoom?.id) return;
    const { permission } = await api(`/api/rooms/${message.room_id}/permission`);
    if (permission === Permission.MEMBER) {
      renderMessage(message);
    } else {
      // membership was dropped elsewhere (e.g. another tab)
      await closeRoom();
      await loadRooms();
    }
  })
);

socket.on("rooms_changed", () => enqueue(loadRooms));

messageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = messageForm.elements.content;
  try {
    await emitAck("send_message", { room_id: activeRoom.id, content: input.value });
    input.value = "";
    errorBox.textContent = "";
  } catch (error) {
    errorBox.textContent = error.message;
  }
});

createRoomForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const input = createRoomForm.elements.display_name;
  enqueue(async () => {
    const room = await api("/api/rooms", { method: "POST", body: { display_name: input.value } });
    input.value = "";
    await openRoom(room);
  });
});

document.getElementById("logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  location.href = "/";
});

enqueue(loadRooms);
