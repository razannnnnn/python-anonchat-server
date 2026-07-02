import os
import psutil
import time
from aiohttp import web
import json
import asyncio

# Hardcoded password untuk admin (bisa diganti atau dipindah ke environment variable)
ADMIN_PASSWORD = "admin"

# Melacak kapan server dinyalakan
SERVER_START_TIME = time.time()

class DashboardServer:
    def __init__(self, clients_ref, rooms_ref, broadcast_online_func, broadcast_room_func, send_func, server_logs_ref, global_bans_ref, server_settings_ref, global_history_ref):
        self.clients = clients_ref
        self.rooms = rooms_ref
        self.broadcast_online = broadcast_online_func
        self.broadcast_room = broadcast_room_func
        self.send = send_func
        self.server_logs = server_logs_ref
        self.global_bans = global_bans_ref
        self.server_settings = server_settings_ref
        self.global_history = global_history_ref
        self.app = web.Application()
        self.setup_routes()

    def setup_routes(self):
        # API Routes
        self.app.router.add_get('/api/stats', self.handle_stats)
        self.app.router.add_post('/api/login', self.handle_login)
        self.app.router.add_post('/api/action', self.handle_action)
        self.app.router.add_get('/api/logs', self.handle_logs)
        self.app.router.add_get('/api/bans', self.handle_bans)

        # Static files (Frontend UI)
        dashboard_dir = os.path.join(os.path.dirname(__file__), 'dashboard')
        if not os.path.exists(dashboard_dir):
            os.makedirs(dashboard_dir)
            
        self.app.router.add_static('/', dashboard_dir, name='static', show_index=True)

    def _check_auth(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header or auth_header != f"Bearer {ADMIN_PASSWORD}":
            return False
        return True

    async def handle_logs(self, request):
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        return web.json_response({"logs": list(self.server_logs)})

    async def handle_bans(self, request):
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        return web.json_response({
            "ips": list(self.global_bans["ips"]),
            "usernames": list(self.global_bans["usernames"])
        })

    async def handle_login(self, request):
        try:
            data = await request.json()
            password = data.get('password')
            if password == ADMIN_PASSWORD:
                return web.json_response({"success": True, "token": ADMIN_PASSWORD})
            else:
                return web.json_response({"success": False, "error": "Invalid password"}, status=401)
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def handle_stats(self, request):
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        # System Metrics
        cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        uptime_seconds = int(time.time() - SERVER_START_TIME)

        # App Metrics
        total_online = len(self.clients)
        
        # Format rooms
        formatted_rooms = []
        for rname, rdata in self.rooms.items():
            count = sum(1 for c in self.clients.values() if c["room"] == rname)
            if rname == "global":
                formatted_rooms.append({
                    "name": "global",
                    "owner": "-",
                    "locked": False,
                    "online": count
                })
            else:
                formatted_rooms.append({
                    "name": rname,
                    "owner": rdata["owner"] if rdata else "-",
                    "locked": bool(rdata and rdata["password_hash"]),
                    "online": count
                })

        # Format users
        formatted_users = []
        for ws, info in self.clients.items():
            formatted_users.append({
                "username": info["username"],
                "room": info["room"],
                "ip": ws.remote_address[0] if ws.remote_address else "Unknown"
            })

        return web.json_response({
            "system": {
                "cpu_percent": cpu_percent,
                "ram_percent": mem.percent,
                "ram_used_mb": mem.used // (1024 * 1024),
                "ram_total_mb": mem.total // (1024 * 1024),
                "uptime_seconds": uptime_seconds,
                "maintenance_mode": self.server_settings["maintenance_mode"]
            },
            "app": {
                "total_online": total_online,
                "total_rooms": len(self.rooms),
                "rooms": formatted_rooms,
                "users": formatted_users
            }
        })

    async def handle_action(self, request):
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            data = await request.json()
            action = data.get("action")

            if action == "kick":
                target_username = data.get("username")
                # Find user websocket
                target_ws = None
                for ws, info in self.clients.items():
                    if info["username"] == target_username:
                        target_ws = ws
                        break
                
                if target_ws:
                    room = self.clients[target_ws]["room"]
                    self.clients[target_ws]["room"] = "global"
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    await self.send(target_ws, {
                        "type": "room_change",
                        "room": "global",
                        "text": "Kamu telah dikick dari server oleh Admin.",
                        "time": timestamp
                    })
                    
                    if room != "global":
                        await self.broadcast_room(room, {
                            "type": "system",
                            "text": f"{target_username} telah dikick oleh Admin",
                            "time": timestamp
                        })
                        await self.broadcast_online(room)
                    
                    await self.broadcast_online("global")
                    return web.json_response({"success": True})
                else:
                    return web.json_response({"success": False, "error": "User not found"})

            elif action == "broadcast":
                message = data.get("message")
                from datetime import datetime
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                # Broadcast to all rooms
                for room in self.rooms.keys():
                    await self.broadcast_room(room, {
                        "type": "system",
                        "text": f"📢 [ADMIN]: {message}",
                        "time": timestamp
                    })
                return web.json_response({"success": True})
                
            elif action == "delete_room":
                room_name = data.get("room")
                if room_name == "global":
                    return web.json_response({"success": False, "error": "Cannot delete global room"})
                
                if room_name in self.rooms:
                    kicked = [ws for ws, c in self.clients.items() if c["room"] == room_name]
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    for ws in kicked:
                        self.clients[ws]["room"] = "global"
                        await self.send(ws, {
                            "type": "room_change",
                            "room": "global",
                            "text": f"Room '{room_name}' dihapus oleh Admin. Kamu dipindahkan ke global.",
                            "time": timestamp
                        })
                    del self.rooms[room_name]
                    await self.broadcast_online("global")
                    return web.json_response({"success": True})
                else:
                    return web.json_response({"success": False, "error": "Room not found"})

            elif action == "global_ban":
                ban_type = data.get("ban_type") # "ip" or "username"
                target = data.get("target")
                if not target:
                    return web.json_response({"success": False, "error": "Target required"})
                if ban_type == "ip":
                    self.global_bans["ips"].add(target)
                else:
                    self.global_bans["usernames"].add(target)
                
                # Kick them if they are online
                kicked_ws = []
                for ws, info in self.clients.items():
                    ip = ws.remote_address[0] if ws.remote_address else ""
                    if (ban_type == "ip" and ip == target) or (ban_type == "username" and info["username"] == target):
                        kicked_ws.append(ws)
                
                for ws in kicked_ws:
                    await self.send(ws, {"type": "system", "text": "Anda telah di-banned secara global oleh Admin."})
                    await ws.close()
                return web.json_response({"success": True})

            elif action == "global_unban":
                ban_type = data.get("ban_type")
                target = data.get("target")
                if ban_type == "ip" and target in self.global_bans["ips"]:
                    self.global_bans["ips"].remove(target)
                elif ban_type == "username" and target in self.global_bans["usernames"]:
                    self.global_bans["usernames"].remove(target)
                return web.json_response({"success": True})

            elif action == "clear_history":
                self.global_history.clear()
                from datetime import datetime
                timestamp = datetime.now().strftime("%H:%M:%S")
                for room in self.rooms.keys():
                    await self.broadcast_room(room, {
                        "type": "system",
                        "text": "📋 Riwayat chat global telah dihapus oleh Admin.",
                        "time": timestamp
                    })
                return web.json_response({"success": True})

            elif action == "toggle_maintenance":
                self.server_settings["maintenance_mode"] = not self.server_settings["maintenance_mode"]
                return web.json_response({"success": True, "maintenance_mode": self.server_settings["maintenance_mode"]})

            return web.json_response({"success": False, "error": "Unknown action"})
            
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)


async def start_dashboard(clients_ref, rooms_ref, broadcast_online_func, broadcast_room_func, send_func, port, server_logs_ref, global_bans_ref, server_settings_ref, global_history_ref):
    dashboard = DashboardServer(clients_ref, rooms_ref, broadcast_online_func, broadcast_room_func, send_func, server_logs_ref, global_bans_ref, server_settings_ref, global_history_ref)
    runner = web.AppRunner(dashboard.app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Dashboard Server berjalan di http://0.0.0.0:{port}")
