import asyncio
import websockets
import json
import random
import string
import re
import hashlib
from datetime import datetime
from collections import deque
from dashboard_server import start_dashboard

clients = {}

rooms = {
    "global": None
}

# ── Global chat history ───────────────────────────────────────
MAX_HISTORY = 200           # max messages to keep
HISTORY_TTL_HOURS = 24      # auto-clear interval
global_history: deque = deque(maxlen=MAX_HISTORY)  # list of message dicts
_history_last_cleared: datetime = datetime.now()

# ── Server State untuk Dashboard ────────────────────────────────
server_logs: deque = deque(maxlen=200)
global_bans = {
    "ips": set(),
    "usernames": set()
}
server_settings = {
    "maintenance_mode": False
}

def log_event(msg):
    print(msg)
    server_logs.append(msg)

def generate_username():
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"Anon-{suffix}"

def is_username_taken(username: str) -> bool:
    return username.lower() in [c["username"].lower() for c in clients.values()]

def sanitize_username(username: str) -> str:
    clean = re.sub(r'[^\w\-]', '', username.strip())
    return clean[:20]

def sanitize_roomname(name: str) -> str:
    clean = re.sub(r'[^\w\-]', '', name.strip().lower())
    return clean[:20]

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def timestamp():
    return datetime.now().strftime("%H:%M:%S")

def online_in_room(room: str) -> int:
    return sum(1 for c in clients.values() if c["room"] == room)

def users_in_room(room: str) -> list:
    """Return sorted list of usernames in a room."""
    return sorted([c["username"] for c in clients.values() if c["room"] == room])

def find_ws_by_username(username: str):
    """Find websocket by username (case-insensitive)."""
    for ws, c in clients.items():
        if c["username"].lower() == username.lower():
            return ws
    return None

async def send(ws, data: dict):
    try:
        await ws.send(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass

async def broadcast_room(room: str, message: dict, exclude=None):
    targets = [ws for ws, c in clients.items() if c["room"] == room and ws != exclude]
    if targets:
        data = json.dumps(message, ensure_ascii=False)
        await asyncio.gather(*[ws.send(data) for ws in targets], return_exceptions=True)

async def broadcast_room_all(room: str, message: dict):
    targets = [ws for ws, c in clients.items() if c["room"] == room]
    if targets:
        data = json.dumps(message, ensure_ascii=False)
        await asyncio.gather(*[ws.send(data) for ws in targets], return_exceptions=True)

async def broadcast_online(room: str):
    """Broadcast online count and user list with public keys to everyone in a room."""
    user_list = users_in_room(room)
    count = len(user_list)
    public_keys = {}
    for c in clients.values():
        if c["room"] == room and c["username"] in user_list and "public_key" in c:
            public_keys[c["username"]] = c["public_key"]
            
    await broadcast_room_all(room, {
        "type": "online",
        "count": count,
        "users": user_list,
        "public_keys": public_keys
    })

async def handle_command(websocket, text: str):
    """Proses command dari user."""
    info = clients[websocket]
    username = info["username"]
    current_room = info["room"]
    parts = text.strip().split()
    cmd = parts[0].lower()

    # /help
    if cmd == "/help":
        await send(websocket, {
            "type": "system",
            "text": (
                "╔══════════════ COMMANDS ══════════════╗\n"
                "║ /buatroom <nama> [password]           ║\n"
                "║   Buat private room                   ║\n"
                "║ /join <nama> [password]               ║\n"
                "║   Masuk ke room                       ║\n"
                "║ /global                               ║\n"
                "║   Kembali ke global room              ║\n"
                "║ /rooms                                ║\n"
                "║   Lihat daftar room                   ║\n"
                "║ /who                                  ║\n"
                "║   Lihat user di room ini              ║\n"
                "║ /w <user> <pesan>                     ║\n"
                "║   Kirim whisper/DM ke user            ║\n"
                "║ /r <pesan>                            ║\n"
                "║   Balas whisper terakhir               ║\n"
                "║ /kick <user>                          ║\n"
                "║   Keluarkan user (owner only)         ║\n"
                "║ /ban <user>                           ║\n"
                "║   Ban user (owner only)               ║\n"
                "║ /unban <user>                         ║\n"
                "║   Unban user (owner only)             ║\n"
                "║ /deleteroom                           ║\n"
                "║   Hapus room kamu (owner only)        ║\n"
                "╚═══════════════════════════════════════╝"
            ),
            "time": timestamp()
        })

    # /rooms
    elif cmd == "/rooms":
        lines = []
        for rname, rdata in rooms.items():
            count = online_in_room(rname)
            if rname == "global":
                lines.append(f"  🌐 global  ({count} online)")
            else:
                lock = "🔒" if rdata and rdata["password_hash"] else "🔓"
                owner = rdata["owner"] if rdata else "-"
                lines.append(f"  {lock} {rname}  ({count} online) — owner: {owner}")
        await send(websocket, {
            "type": "system",
            "text": "Daftar room:\n" + "\n".join(lines),
            "time": timestamp()
        })

    # /who
    elif cmd == "/who":
        members = users_in_room(current_room)
        await send(websocket, {
            "type": "system",
            "text": f"Online di [{current_room}]: " + ", ".join(members),
            "time": timestamp()
        })

    # /global
    elif cmd == "/global":
        if current_room == "global":
            await send(websocket, {"type": "system", "text": "Kamu sudah di global room.", "time": timestamp()})
            return
        old_room = current_room
        clients[websocket]["room"] = "global"
        await broadcast_room(old_room, {
            "type": "system",
            "text": f"{username} meninggalkan room ini",
            "time": timestamp()
        })
        await broadcast_online(old_room)
        await send(websocket, {
            "type": "room_change",
            "room": "global",
            "text": "Kamu pindah ke global room.",
            "time": timestamp()
        })
        await broadcast_room("global", {
            "type": "system",
            "text": f"{username} bergabung ke global",
            "time": timestamp()
        }, exclude=websocket)
        await broadcast_online("global")

    # /buatroom <nama> [password]
    elif cmd == "/buatroom":
        if len(parts) < 2:
            await send(websocket, {"type": "system", "text": "Usage: /buatroom <nama> [password]", "time": timestamp()})
            return
        rname = sanitize_roomname(parts[1])
        if not rname:
            await send(websocket, {"type": "system", "text": "Nama room tidak valid.", "time": timestamp()})
            return
        if rname in rooms:
            await send(websocket, {"type": "system", "text": f"Room '{rname}' sudah ada.", "time": timestamp()})
            return
        pw = parts[2] if len(parts) >= 3 else None
        rooms[rname] = {
            "password_hash": hash_password(pw) if pw else None,
            "owner": username,
            "members": set(),
            "banned_users": set()
        }
        # Pindahkan creator ke room baru
        old_room = current_room
        clients[websocket]["room"] = rname
        await broadcast_room(old_room, {
            "type": "system",
            "text": f"{username} meninggalkan room ini",
            "time": timestamp()
        })
        await broadcast_online(old_room)
        lock_info = f"🔒 dengan password" if pw else "🔓 tanpa password"
        await send(websocket, {
            "type": "room_change",
            "room": rname,
            "text": f"Room '{rname}' berhasil dibuat ({lock_info}). Kamu otomatis masuk.",
            "time": timestamp()
        })
        await broadcast_online(rname)
        log_event(f"[{timestamp()}] Room '{rname}' dibuat oleh {username}")

    # /join <nama> [password]
    elif cmd == "/join":
        if len(parts) < 2:
            await send(websocket, {"type": "system", "text": "Usage: /join <nama> [password]", "time": timestamp()})
            return
        rname = sanitize_roomname(parts[1])
        if rname not in rooms:
            await send(websocket, {"type": "system", "text": f"Room '{rname}' tidak ditemukan. Ketik /rooms untuk lihat daftar.", "time": timestamp()})
            return
        if rname == current_room:
            await send(websocket, {"type": "system", "text": f"Kamu sudah di room '{rname}'.", "time": timestamp()})
            return
        rdata = rooms[rname]
        if rdata and "banned_users" in rdata and username in rdata["banned_users"]:
            await send(websocket, {"type": "system", "text": f"Kamu telah di-banned dari room '{rname}'.", "time": timestamp()})
            return
        if rdata and rdata["password_hash"]:
            pw = parts[2] if len(parts) >= 3 else ""
            if hash_password(pw) != rdata["password_hash"]:
                await send(websocket, {"type": "system", "text": "Password salah.", "time": timestamp()})
                return
        old_room = current_room
        clients[websocket]["room"] = rname
        await broadcast_room(old_room, {
            "type": "system",
            "text": f"{username} meninggalkan room ini",
            "time": timestamp()
        })
        await broadcast_online(old_room)
        await send(websocket, {
            "type": "room_change",
            "room": rname,
            "text": f"Kamu masuk ke room '{rname}'.",
            "time": timestamp()
        })
        await broadcast_room(rname, {
            "type": "system",
            "text": f"{username} bergabung ke room ini",
            "time": timestamp()
        }, exclude=websocket)
        await broadcast_online(rname)

    # /deleteroom
    elif cmd == "/deleteroom":
        if current_room == "global":
            await send(websocket, {"type": "system", "text": "Global room tidak bisa dihapus.", "time": timestamp()})
            return
        rdata = rooms.get(current_room)
        if not rdata or rdata["owner"] != username:
            await send(websocket, {"type": "system", "text": "Hanya owner yang bisa menghapus room.", "time": timestamp()})
            return
        # Keluarkan semua member ke global
        kicked = [ws for ws, c in clients.items() if c["room"] == current_room]
        rname = current_room
        for ws in kicked:
            clients[ws]["room"] = "global"
            await send(ws, {
                "type": "room_change",
                "room": "global",
                "text": f"Room '{rname}' dihapus oleh owner. Kamu dipindahkan ke global.",
                "time": timestamp()
            })
        del rooms[rname]
        await broadcast_online("global")
        log_event(f"[{timestamp()}] Room '{rname}' dihapus oleh {username}")

    # /kick <username>
    elif cmd == "/kick":
        if current_room == "global":
            await send(websocket, {"type": "system", "text": "Tidak bisa menggunakan /kick di global room.", "time": timestamp()})
            return
        rdata = rooms.get(current_room)
        if not rdata or rdata["owner"] != username:
            await send(websocket, {"type": "system", "text": "Hanya owner yang bisa melakukan kick.", "time": timestamp()})
            return
        if len(parts) < 2:
            await send(websocket, {"type": "system", "text": "Usage: /kick <username>", "time": timestamp()})
            return
        target_name = parts[1]
        target_ws = find_ws_by_username(target_name)
        if not target_ws or clients[target_ws]["room"] != current_room:
            await send(websocket, {"type": "system", "text": f"User '{target_name}' tidak ada di room ini.", "time": timestamp()})
            return
        if target_name == username:
            await send(websocket, {"type": "system", "text": "Tidak bisa kick diri sendiri.", "time": timestamp()})
            return
        
        # Kick target
        clients[target_ws]["room"] = "global"
        await send(target_ws, {
            "type": "room_change",
            "room": "global",
            "text": f"Kamu telah dikick dari room '{current_room}' oleh owner.",
            "time": timestamp()
        })
        await broadcast_room(current_room, {
            "type": "system",
            "text": f"{target_name} telah dikick dari room",
            "time": timestamp()
        })
        await broadcast_online(current_room)
        await broadcast_online("global")

    # /ban <username>
    elif cmd == "/ban":
        if current_room == "global":
            await send(websocket, {"type": "system", "text": "Tidak bisa menggunakan /ban di global room.", "time": timestamp()})
            return
        rdata = rooms.get(current_room)
        if not rdata or rdata["owner"] != username:
            await send(websocket, {"type": "system", "text": "Hanya owner yang bisa melakukan ban.", "time": timestamp()})
            return
        if len(parts) < 2:
            await send(websocket, {"type": "system", "text": "Usage: /ban <username>", "time": timestamp()})
            return
        target_name = parts[1]
        if target_name == username:
            await send(websocket, {"type": "system", "text": "Tidak bisa ban diri sendiri.", "time": timestamp()})
            return
            
        rdata.setdefault("banned_users", set()).add(target_name)
        await send(websocket, {"type": "system", "text": f"User '{target_name}' berhasil dibanned dari room ini.", "time": timestamp()})
        
        # Kick if they are currently in the room
        target_ws = find_ws_by_username(target_name)
        if target_ws and clients[target_ws]["room"] == current_room:
            clients[target_ws]["room"] = "global"
            await send(target_ws, {
                "type": "room_change",
                "room": "global",
                "text": f"Kamu telah dibanned dari room '{current_room}' oleh owner.",
                "time": timestamp()
            })
            await broadcast_room(current_room, {
                "type": "system",
                "text": f"{target_name} telah dibanned dari room",
                "time": timestamp()
            })
            await broadcast_online(current_room)
            await broadcast_online("global")

    # /unban <username>
    elif cmd == "/unban":
        if current_room == "global":
            await send(websocket, {"type": "system", "text": "Tidak bisa menggunakan /unban di global room.", "time": timestamp()})
            return
        rdata = rooms.get(current_room)
        if not rdata or rdata["owner"] != username:
            await send(websocket, {"type": "system", "text": "Hanya owner yang bisa melakukan unban.", "time": timestamp()})
            return
        if len(parts) < 2:
            await send(websocket, {"type": "system", "text": "Usage: /unban <username>", "time": timestamp()})
            return
        target_name = parts[1]
        if "banned_users" in rdata and target_name in rdata["banned_users"]:
            rdata["banned_users"].remove(target_name)
            await send(websocket, {"type": "system", "text": f"Ban untuk user '{target_name}' telah dicabut.", "time": timestamp()})
        else:
            await send(websocket, {"type": "system", "text": f"User '{target_name}' tidak ada di daftar ban.", "time": timestamp()})

    # /w <username> <message> — Whisper
    elif cmd == "/w":
        if len(parts) < 3:
            await send(websocket, {"type": "system", "text": "Usage: /w <username> <pesan>", "time": timestamp()})
            return
        target_name = parts[1]
        whisper_text = " ".join(parts[2:])
        if len(whisper_text) > 500:
            whisper_text = whisper_text[:500] + "..."
        target_ws = find_ws_by_username(target_name)
        if target_ws is None:
            await send(websocket, {
                "type": "whisper_error",
                "text": f"User '{target_name}' tidak ditemukan atau sedang offline.",
                "time": timestamp()
            })
            return
        if target_ws == websocket:
            await send(websocket, {
                "type": "whisper_error",
                "text": "Tidak bisa mengirim whisper ke diri sendiri.",
                "time": timestamp()
            })
            return
        target_info = clients[target_ws]
        # Send to target
        await send(target_ws, {
            "type": "whisper",
            "from": username,
            "text": whisper_text,
            "time": timestamp()
        })
        # Echo back to sender
        await send(websocket, {
            "type": "whisper_sent",
            "to": target_info["username"],
            "text": whisper_text,
            "time": timestamp()
        })
        log_event(f"[{timestamp()}] [WHISPER] {username} → {target_info['username']}: {whisper_text}")

    # /r <message> — Reply to last whisper
    elif cmd == "/r":
        if len(parts) < 2:
            await send(websocket, {"type": "system", "text": "Usage: /r <pesan>", "time": timestamp()})
            return
        # We track last_whisper_from on the server side
        last_from = info.get("last_whisper_from")
        if not last_from:
            await send(websocket, {
                "type": "whisper_error",
                "text": "Belum ada whisper yang bisa dibalas.",
                "time": timestamp()
            })
            return
        whisper_text = " ".join(parts[1:])
        if len(whisper_text) > 500:
            whisper_text = whisper_text[:500] + "..."
        target_ws = find_ws_by_username(last_from)
        if target_ws is None:
            await send(websocket, {
                "type": "whisper_error",
                "text": f"User '{last_from}' sudah offline.",
                "time": timestamp()
            })
            return
        target_info = clients[target_ws]
        await send(target_ws, {
            "type": "whisper",
            "from": username,
            "text": whisper_text,
            "time": timestamp()
        })
        await send(websocket, {
            "type": "whisper_sent",
            "to": target_info["username"],
            "text": whisper_text,
            "time": timestamp()
        })
        log_event(f"[{timestamp()}] [WHISPER] {username} → {target_info['username']}: {whisper_text}")

    else:
        await send(websocket, {"type": "system", "text": f"Command tidak dikenal: {cmd}. Ketik /help.", "time": timestamp()})

async def handler(websocket):
    ip = websocket.remote_address[0] if websocket.remote_address else "Unknown"
    
    if server_settings["maintenance_mode"]:
        await send(websocket, {"type": "system", "text": "Server sedang dalam Maintenance Mode. Tidak dapat menerima koneksi baru."})
        await asyncio.sleep(0.5)
        await websocket.close()
        return
        
    if ip in global_bans["ips"]:
        await websocket.close()
        return

    # Minta username
    await send(websocket, {"type": "request_username", "text": "Masukkan username (Enter untuk random):"})

    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=30)
        data = json.loads(raw)
        if data.get("type") != "set_username":
            return

        requested = sanitize_username(data.get("username", ""))
        if not requested:
            username = generate_username()
        elif is_username_taken(requested):
            suffix = ''.join(random.choices(string.digits, k=3))
            username = f"{requested}_{suffix}"
        else:
            username = requested

    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
        return

    if username.lower() in [u.lower() for u in global_bans["usernames"]]:
        await send(websocket, {"type": "system", "text": "Anda telah dibanned secara global dari server ini."})
        await asyncio.sleep(0.5)
        await websocket.close()
        return

    public_key = data.get("public_key", "")
    clients[websocket] = {"username": username, "room": "global", "public_key": public_key}
    log_event(f"[{timestamp()}] + {username} joined (IP: {ip}, PK: {'Yes' if public_key else 'No'})")

    name_info = "" if username == (sanitize_username(data.get("username", "")) or username) else f" (username sudah dipakai, diganti menjadi {username})"
    await send(websocket, {
        "type": "welcome",
        "username": username,
        "room": "global",
        "text": f"Selamat datang, {username}!{name_info}\nKetik /help untuk melihat commands.",
        "time": timestamp()
    })

    # Send global chat history to the new user
    if global_history:
        await send(websocket, {
            "type": "history",
            "messages": list(global_history)
        })

    await broadcast_room("global", {
        "type": "system",
        "text": f"{username} bergabung ke global",
        "time": timestamp()
    }, exclude=websocket)

    # Broadcast updated online list
    await broadcast_online("global")

    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "message":
                text = data.get("text", "").strip()
                if not text:
                    continue
                if text.startswith("/"):
                    await handle_command(websocket, text)
                else:
                    if len(text) > 500:
                        text = text[:500] + "..."
                    room = clients[websocket]["room"]
                    username = clients[websocket]["username"]
                    log_event(f"[{timestamp()}] [{room}] {username}: {text}")
                    msg_data = {
                        "type": "message",
                        "from": username,
                        "text": text,
                        "time": timestamp(),
                        "room": room
                    }
                    await broadcast_room_all(room, msg_data)
                    # Store in global history (skip private room markers)
                    if room == "global" and not text.startswith("[[ROOM:"):
                        global_history.append(msg_data)

            elif msg_type == "whisper":
                # Client-side whisper: route /w command through message type
                target_name = data.get("to", "").strip()
                whisper_text = data.get("text", "").strip()
                if not target_name or not whisper_text:
                    continue
                if len(whisper_text) > 500:
                    whisper_text = whisper_text[:500] + "..."
                username = clients[websocket]["username"]
                target_ws = find_ws_by_username(target_name)
                if target_ws is None:
                    await send(websocket, {
                        "type": "whisper_error",
                        "text": f"User '{target_name}' tidak ditemukan atau sedang offline.",
                        "time": timestamp()
                    })
                    continue
                if target_ws == websocket:
                    await send(websocket, {
                        "type": "whisper_error",
                        "text": "Tidak bisa mengirim whisper ke diri sendiri.",
                        "time": timestamp()
                    })
                    continue
                target_info = clients[target_ws]
                # Track last whisper for /r command
                if "last_whisper_from" not in clients[target_ws]:
                    clients[target_ws]["last_whisper_from"] = None
                clients[target_ws]["last_whisper_from"] = username
                await send(target_ws, {
                    "type": "whisper",
                    "from": username,
                    "text": whisper_text,
                    "time": timestamp()
                })
                await send(websocket, {
                    "type": "whisper_sent",
                    "to": target_info["username"],
                    "text": whisper_text,
                    "time": timestamp()
                })
                log_event(f"[{timestamp()}] [WHISPER] {username} → {target_info['username']}: {whisper_text}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if websocket in clients:
            info = clients[websocket]
            username = info["username"]
            room = info["room"]
            del clients[websocket]
            log_event(f"[{timestamp()}] - {username} left")
            await broadcast_room(room, {
                "type": "system",
                "text": f"{username} meninggalkan room",
                "time": timestamp()
            })
            # Broadcast updated online list
            await broadcast_online(room)

async def clear_history_loop():
    """Auto-clear global chat history every 24 hours."""
    global _history_last_cleared
    while True:
        await asyncio.sleep(60)  # check every minute
        now = datetime.now()
        elapsed = (now - _history_last_cleared).total_seconds()
        if elapsed >= HISTORY_TTL_HOURS * 3600:
            global_history.clear()
            _history_last_cleared = now
            log_event(f"[{timestamp()}] 🗑 Global history cleared (24h reset)")
            await broadcast_room_all("global", {
                "type": "system",
                "text": "📋 Riwayat chat global telah direset (24 jam).",
                "time": timestamp()
            })

async def main():
    log_event("Chat Server berjalan di ws://0.0.0.0:8765")
    log_event(f"History: max {MAX_HISTORY} pesan, reset setiap {HISTORY_TTL_HOURS} jam")
    log_event("-" * 40)
    # Start history cleaner in the background
    asyncio.create_task(clear_history_loop())
    
    # Start Dashboard Server
    asyncio.create_task(start_dashboard(
        clients_ref=clients,
        rooms_ref=rooms,
        broadcast_online_func=broadcast_online,
        broadcast_room_func=broadcast_room,
        send_func=send,
        port=8080,
        server_logs_ref=server_logs,
        global_bans_ref=global_bans,
        server_settings_ref=server_settings,
        global_history_ref=global_history
    ))

    async with websockets.serve(handler, "0.0.0.0", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())