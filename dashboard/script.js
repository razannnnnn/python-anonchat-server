document.addEventListener('DOMContentLoaded', () => {
    
    // --- DOM Elements ---
    const loginOverlay = document.getElementById('loginOverlay');
    const dashboardApp = document.getElementById('dashboardApp');
    const loginForm = document.getElementById('loginForm');
    const passwordInput = document.getElementById('passwordInput');
    const loginError = document.getElementById('loginError');
    const logoutBtn = document.getElementById('logoutBtn');
    
    const navItems = document.querySelectorAll('.nav-item');
    const tabContents = document.querySelectorAll('.tab-content');
    const currentTabTitle = document.getElementById('currentTabTitle');
    
    // Metrics
    const cpuMetric = document.getElementById('cpuMetric');
    const cpuBar = document.getElementById('cpuBar');
    const ramMetric = document.getElementById('ramMetric');
    const ramBar = document.getElementById('ramBar');
    const usersMetric = document.getElementById('usersMetric');
    const roomsMetric = document.getElementById('roomsMetric');
    const serverUptime = document.getElementById('serverUptime');
    
    // Tables & Badges
    const usersTableBody = document.getElementById('usersTableBody');
    const totalUsersBadge = document.getElementById('totalUsersBadge');
    const roomsTableBody = document.getElementById('roomsTableBody');
    const totalRoomsBadge = document.getElementById('totalRoomsBadge');
    
    // Forms
    const broadcastForm = document.getElementById('broadcastForm');
    const broadcastMessage = document.getElementById('broadcastMessage');
    
    // Console
    const consoleOutput = document.getElementById('consoleOutput');
    
    // Bans
    const banForm = document.getElementById('banForm');
    const banType = document.getElementById('banType');
    const banTarget = document.getElementById('banTarget');
    const bannedIpsList = document.getElementById('bannedIpsList');
    const bannedUsernamesList = document.getElementById('bannedUsernamesList');

    // Settings
    const btnMaintenance = document.getElementById('btnMaintenance');
    const btnClearHistory = document.getElementById('btnClearHistory');

    // Toast
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toastMessage');
    const toastIcon = toast.querySelector('i');

    // --- Chart Initialization ---
    const ctx = document.getElementById('metricsChart').getContext('2d');
    
    // Nord Colors for Chart
    const nord8 = '#88C0D0'; // Primary
    const nord15 = '#B48EAD'; // Purple
    const nord3 = '#4C566A'; // Grid lines
    const nord6 = '#ECEFF4'; // Text
    
    const maxDataPoints = 20; // Show last ~40 seconds
    const metricsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array(maxDataPoints).fill(''),
            datasets: [
                {
                    label: 'CPU Usage (%)',
                    data: Array(maxDataPoints).fill(0),
                    borderColor: nord8,
                    backgroundColor: 'rgba(136, 192, 208, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0
                },
                {
                    label: 'RAM Usage (%)',
                    data: Array(maxDataPoints).fill(0),
                    borderColor: nord15,
                    backgroundColor: 'rgba(180, 142, 173, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 0 // Disable animation for smoother polling updates
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: nord3, drawBorder: false },
                    ticks: { color: nord6 }
                },
                x: {
                    grid: { display: false, drawBorder: false },
                    ticks: { display: false }
                }
            },
            plugins: {
                legend: {
                    labels: { color: nord6, font: { family: 'Inter' } }
                }
            }
        }
    });

    // --- State ---
    let authToken = localStorage.getItem('anonchat_admin_token');
    let pollingInterval = null;

    // --- Initialization ---
    if (authToken) {
        checkAuth();
    }

    // --- Authentication ---
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const password = passwordInput.value;
        loginError.textContent = '';
        
        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });
            
            const data = await res.json();
            if (data.success) {
                authToken = data.token;
                localStorage.setItem('anonchat_admin_token', authToken);
                loginOverlay.classList.remove('active');
                dashboardApp.classList.remove('hidden');
                startPolling();
                showToast('Login successful', 'success');
            } else {
                loginError.textContent = data.error || 'Invalid password';
            }
        } catch (err) {
            loginError.textContent = 'Server connection failed';
        }
    });

    logoutBtn.addEventListener('click', () => {
        authToken = null;
        localStorage.removeItem('anonchat_admin_token');
        stopPolling();
        dashboardApp.classList.add('hidden');
        loginOverlay.classList.add('active');
        passwordInput.value = '';
    });

    async function checkAuth() {
        // Test token with a quick stats fetch
        try {
            const res = await fetch('/api/stats', {
                headers: { 'Authorization': `Bearer ${authToken}` }
            });
            if (res.ok) {
                loginOverlay.classList.remove('active');
                dashboardApp.classList.remove('hidden');
                updateDashboard(await res.json());
                startPolling();
            } else {
                // Token invalid
                logoutBtn.click();
            }
        } catch (err) {
            console.error('Cannot connect to server', err);
        }
    }

    // --- Navigation ---
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabId = item.getAttribute('data-tab');
            
            // Update Active Nav
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');
            
            // Update Title
            currentTabTitle.textContent = item.textContent.trim();
            
            // Switch Tab Content
            tabContents.forEach(tab => {
                if (tab.id === `tab-${tabId}`) {
                    tab.classList.add('active');
                    tab.classList.remove('hidden');
                    
                    if(tabId === 'bans') fetchBans();
                    if(tabId === 'console') fetchLogs();
                } else {
                    tab.classList.remove('active');
                    tab.classList.add('hidden');
                }
            });
        });
    });

    // --- Data Polling ---
    function startPolling() {
        if (!pollingInterval) {
            fetchStats(); // immediate fetch
            fetchLogs();
            pollingInterval = setInterval(() => {
                fetchStats();
                // Hanya update console jika tab aktif
                const activeTab = document.querySelector('.nav-item.active').getAttribute('data-tab');
                if (activeTab === 'console') fetchLogs();
            }, 2000); // Poll every 2 seconds
        }
    }

    function stopPolling() {
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
    }

    async function fetchStats() {
        try {
            const res = await fetch('/api/stats', {
                headers: { 'Authorization': `Bearer ${authToken}` }
            });
            
            if (res.status === 401) {
                logoutBtn.click();
                return;
            }
            
            if (res.ok) {
                const data = await res.json();
                updateDashboard(data);
            }
        } catch (err) {
            console.error('Error fetching stats:', err);
        }
    }

    function formatUptime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }

    function updateDashboard(data) {
        // System Metrics
        cpuMetric.textContent = `${data.system.cpu_percent}%`;
        cpuBar.style.width = `${data.system.cpu_percent}%`;
        
        ramMetric.textContent = `${data.system.ram_used_mb} MB`;
        ramBar.style.width = `${data.system.ram_percent}%`;
        
        serverUptime.textContent = `Uptime: ${formatUptime(data.system.uptime_seconds)}`;
        
        if(data.system.maintenance_mode) {
            btnMaintenance.textContent = "Disable Maintenance Mode";
            btnMaintenance.classList.replace('btn-outline', 'btn-primary');
        } else {
            btnMaintenance.textContent = "Enable Maintenance Mode";
            btnMaintenance.classList.replace('btn-primary', 'btn-outline');
        }
        
        // Update Chart
        const timeLabel = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute:'2-digit', second:'2-digit' });
        
        // Remove oldest data point
        metricsChart.data.labels.shift();
        metricsChart.data.datasets[0].data.shift();
        metricsChart.data.datasets[1].data.shift();
        
        // Add new data point
        metricsChart.data.labels.push(timeLabel);
        metricsChart.data.datasets[0].data.push(data.system.cpu_percent);
        metricsChart.data.datasets[1].data.push(data.system.ram_percent);
        metricsChart.update();
        
        // App Metrics
        usersMetric.textContent = data.app.total_online;
        roomsMetric.textContent = data.app.total_rooms;
        
        // Update Users Table
        totalUsersBadge.textContent = `${data.app.users.length} Users`;
        usersTableBody.innerHTML = '';
        if (data.app.users.length === 0) {
            usersTableBody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No users online</td></tr>`;
        } else {
            data.app.users.forEach(user => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${user.username}</strong></td>
                    <td><span class="badge">${user.room}</span></td>
                    <td class="text-muted">${user.ip}</td>
                    <td>
                        <button class="btn-danger btn-kick" data-username="${user.username}">
                            <i class="fa-solid fa-user-slash"></i> Kick
                        </button>
                    </td>
                `;
                usersTableBody.appendChild(tr);
            });
        }

        // Update Rooms Table
        totalRoomsBadge.textContent = `${data.app.rooms.length} Rooms`;
        roomsTableBody.innerHTML = '';
        data.app.rooms.forEach(room => {
            const statusClass = room.locked ? 'locked' : 'open';
            const statusIcon = room.locked ? 'fa-lock' : 'fa-unlock';
            const statusText = room.locked ? 'Locked' : 'Open';
            
            const isGlobal = room.name === 'global';
            
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${room.name}</strong> ${isGlobal ? '<i class="fa-solid fa-globe text-muted"></i>' : ''}</td>
                <td>${room.owner}</td>
                <td><span class="status-badge ${statusClass}"><i class="fa-solid ${statusIcon}"></i> ${statusText}</span></td>
                <td>${room.online}</td>
                <td>
                    ${!isGlobal ? `<button class="btn-danger btn-del-room" data-room="${room.name}"><i class="fa-solid fa-trash"></i> Delete</button>` : '<span class="text-muted">-</span>'}
                </td>
            `;
            roomsTableBody.appendChild(tr);
        });

        // Re-attach event listeners for new buttons
        attachActionListeners();
    }

    // --- Actions & New Features ---
    async function fetchLogs() {
        try {
            const res = await fetch('/api/logs', {
                headers: { 'Authorization': `Bearer ${authToken}` }
            });
            if (res.ok) {
                const data = await res.json();
                consoleOutput.textContent = data.logs.join('\n');
                consoleOutput.scrollTop = consoleOutput.scrollHeight;
            }
        } catch (err) {}
    }

    async function fetchBans() {
        try {
            const res = await fetch('/api/bans', {
                headers: { 'Authorization': `Bearer ${authToken}` }
            });
            if (res.ok) {
                const data = await res.json();
                bannedIpsList.innerHTML = '';
                bannedUsernamesList.innerHTML = '';
                
                if (data.ips.length === 0) bannedIpsList.innerHTML = '<li class="text-muted">Kosong</li>';
                data.ips.forEach(ip => {
                    const li = document.createElement('li');
                    li.className = 'ban-list-item';
                    li.innerHTML = `<span>${ip}</span> <button class="btn-outline btn-sm btn-unban" data-type="ip" data-target="${ip}">Unban</button>`;
                    bannedIpsList.appendChild(li);
                });
                
                if (data.usernames.length === 0) bannedUsernamesList.innerHTML = '<li class="text-muted">Kosong</li>';
                data.usernames.forEach(uname => {
                    const li = document.createElement('li');
                    li.className = 'ban-list-item';
                    li.innerHTML = `<span>${uname}</span> <button class="btn-outline btn-sm btn-unban" data-type="username" data-target="${uname}">Unban</button>`;
                    bannedUsernamesList.appendChild(li);
                });

                document.querySelectorAll('.btn-unban').forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        e.preventDefault();
                        const type = btn.getAttribute('data-type');
                        const target = btn.getAttribute('data-target');
                        sendAction('global_unban', { ban_type: type, target: target }).then(() => fetchBans());
                    });
                });
            }
        } catch (err) {}
    }

    banForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const type = banType.value;
        const target = banTarget.value.trim();
        if (target) {
            sendAction('global_ban', { ban_type: type, target: target }).then(() => {
                banTarget.value = '';
                fetchBans();
            });
        }
    });

    btnMaintenance.addEventListener('click', () => {
        sendAction('toggle_maintenance', {}).then(() => fetchStats());
    });

    btnClearHistory.addEventListener('click', () => {
        if(confirm("Apakah Anda yakin ingin menghapus seluruh riwayat chat global? Tindakan ini tidak dapat dibatalkan.")) {
            sendAction('clear_history', {});
        }
    });

    function attachActionListeners() {
        document.querySelectorAll('.btn-kick').forEach(btn => {
            btn.addEventListener('click', () => {
                const username = btn.getAttribute('data-username');
                if (confirm(`Are you sure you want to kick ${username}?`)) {
                    sendAction('kick', { username });
                }
            });
        });

        document.querySelectorAll('.btn-del-room').forEach(btn => {
            btn.addEventListener('click', () => {
                const room = btn.getAttribute('data-room');
                if (confirm(`Are you sure you want to delete room '${room}'? All users will be moved to global.`)) {
                    sendAction('delete_room', { room });
                }
            });
        });
    }

    broadcastForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const message = broadcastMessage.value.trim();
        if (message) {
            sendAction('broadcast', { message });
            broadcastMessage.value = '';
        }
    });

    async function sendAction(actionType, payload) {
        try {
            const res = await fetch('/api/action', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authToken}`
                },
                body: JSON.stringify({ action: actionType, ...payload })
            });
            
            const data = await res.json();
            if (data.success) {
                showToast(`Action '${actionType}' executed successfully`, 'success');
                fetchStats(); // immediate update
            } else {
                showToast(`Error: ${data.error}`, 'error');
            }
        } catch (err) {
            showToast('Failed to connect to server', 'error');
        }
    }

    // --- Toast Notification ---
    function showToast(message, type = 'success') {
        toastMessage.textContent = message;
        
        if (type === 'error') {
            toast.classList.add('error');
            toastIcon.className = 'fa-solid fa-circle-exclamation';
        } else {
            toast.classList.remove('error');
            toastIcon.className = 'fa-solid fa-check-circle';
        }
        
        toast.classList.add('show');
        
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }
});
