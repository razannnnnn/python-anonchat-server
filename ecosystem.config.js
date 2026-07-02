module.exports = {
  apps: [{
    name: "anonchat-server",
    script: "./server.py",
    interpreter: "python3", // Pastikan menggunakan python3 di STB (Linux/Armbian)
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: "300M", // Batas memori agar tidak memberatkan STB (300 MB)
    env: {
      NODE_ENV: "production"
    }
  }]
}
