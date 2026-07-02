# Python AnonChat 🕵️‍♂️💬

AnonChat adalah aplikasi obrolan anonim berbasis Terminal User Interface (TUI) yang mengedepankan privasi, keamanan, dan desain UI yang elegan. Dibangun menggunakan Python dengan *framework* **Textual** untuk antarmuka terminal yang modern dan **WebSockets** untuk komunikasi *real-time*.

## ✨ Fitur Utama

- **Antarmuka Terminal (TUI) Modern**: Antarmuka interaktif yang responsif dengan sidebar, log chat yang rapi, dan indikator status *real-time*.
- **Global & Private Rooms**: Ngobrol bebas di ruang publik atau buat *private room* rahasia dengan perlindungan *password*.
- **End-to-End Encryption (E2E)**: Pesan di dalam *private room* dienkripsi secara lokal menggunakan AES (kriptografi Fernet). Server sama sekali tidak bisa membaca isi obrolan.
- **Room Moderation**: Pembuat *private room* memiliki kuasa penuh untuk mengeluarkan (`/kick`) atau memblokir (`/ban`) pengguna lain.
- **Whisper (Direct Messages)**: Kirim pesan pribadi langsung ke *user* tertentu di dalam room.
- **Self-Destructing Messages**: Kirim pesan sementara menggunakan `/burn <detik> <pesan>` yang akan terhapus otomatis dari klien penerima setelah waktu habis.
- **Smart Features**: Notifikasi *@mention* terminal (*bell*), indikator ping latensi jaringan, navigasi riwayat input menggunakan *Arrow Keys* (↑ / ↓), dan *Auto-Reconnect*.

## 🚀 Cara Instalasi

Pastikan kamu sudah menginstal **Python 3.8+**.

1. Clone repositori ini:
   ```bash
   git clone https://github.com/username/python-anonchat.git
   cd python-anonchat
   ```

2. Instal dependensi yang dibutuhkan:
   ```bash
   pip install textual websockets cryptography
   ```

## 🛠️ Cara Menggunakan

Sistem ini terbagi menjadi 2 bagian: **Server** dan **Client**.

### Menjalankan Server
Server bertanggung jawab mengatur perutean (*routing*) pesan dan mengelola status *room*.
```bash
python server/server.py
```
*Server akan berjalan secara default di `ws://0.0.0.0:8765`.*

### Menjalankan Client
Client adalah antarmuka terminal tempat kamu mengobrol.
```bash
python client/main.py ws://localhost:8765
```
*(Ganti `ws://localhost:8765` dengan URL atau IP server publik milikmu jika server dijalankan di *cloud*)*

## 📜 Panduan Perintah (Commands)

Ketikkan perintah berikut di input chat:

| Perintah | Deskripsi |
|---|---|
| `/help` | Menampilkan pesan bantuan |
| `/clear` | Membersihkan layar obrolan lokal |
| `/quit` | Keluar dari aplikasi |
| `/create <room> <pass>` | Membuat private room dengan password |
| `/join <room> <pass>` | Masuk ke private room dengan password |
| `/leave` | Keluar dari private room (kembali ke global) |
| `/w <user> <pesan>` | Kirim pesan rahasia (whisper) ke user tertentu |
| `/r <pesan>` | Balas whisper terakhir yang masuk |
| `/kick <user>` | Keluarkan user dari room *(Hanya owner room)* |
| `/ban <user>` | Blokir user dari room *(Hanya owner room)* |
| `/unban <user>` | Buka blokir user dari room *(Hanya owner room)* |
| `/burn <detik> <pesan>` | Kirim pesan yang otomatis hilang setelah sekian detik |
| `/me <aksi>` | Kirim pesan aksi bergaya roleplay |
| `/shrug` | Kirim emoticon ¯\\_(ツ)_/¯ |

**Shortcut UI:**
- **Ctrl+U**: Buka/Tutup Sidebar user online.
- **Ctrl+C**: Paksa keluar (Quit).
- **↑ / ↓**: Navigasi riwayat pesan sebelumnya/selanjutnya.

## 📁 Struktur Kode

Aplikasi telah direfaktor agar *Pythonic* dan modular:
- `client/`: Berisi UI (`app.py`), logika *WebSocket* (`message_handler.py`), parser perintah (`commands.py`), dan keamanan (`crypto.py`).
- `server/`: Berisi skrip *backend* untuk perutean data.

---
*Dibuat dengan ❤️ untuk eksplorasi Textual & WebSockets.*
