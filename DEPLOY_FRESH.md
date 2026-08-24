# 🚀 DEPLOY FRESH — BPF WorkHub

Panduan lengkap deployment di server baru (Ubuntu/Debian).

---

## Prasyarat

- **OS**: Ubuntu 22.04+ / Debian 12+
- **RAM**: Minimal 2GB
- **Disk**: Minimal 20GB
- **Docker**: v24+ & Docker Compose v2
- **Domain**: DNS sudah pointing ke IP server (opsional, untuk HTTPS)

---

## 1. Install Docker & Docker Compose

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh

# Install Docker Compose plugin
sudo apt install -y docker-compose-plugin

# Verify
docker --version
docker compose version

# Add user to docker group (agar tanpa sudo)
sudo usermod -aG docker $USER
newgrp docker
```

---

## 2. Clone Repository

```bash
cd /home/$USER
git clone https://github.com/bestprofitsurabaya/bpf-workhub.git
cd bpf-workhub
```

---

## 3. Buat File .env

```bash
# Generate SECRET_KEY acak
SECRET_KEY=$(openssl rand -hex 32)

# Buat .env
cat > .env << EOF
SECRET_KEY=${SECRET_KEY}
EOF

echo "✅ .env created with SECRET_KEY"
```

---

## 4. Generate SSL Certificate

### Option A: Self-Signed (Development)

```bash
chmod +x scripts/gen-selfsigned-cert.sh
bash scripts/gen-selfsigned-cert.sh
```

### Option B: Let's Encrypt (Production)

```bash
# Install certbot
sudo apt install -y certbot

# Generate certificate (ganti domain.com dengan domain anda)
sudo certbot certonly --standalone -d domain.com

# Copy ke direktori certs/
mkdir -p certs
sudo cp /etc/letsencrypt/live/domain.com/fullchain.pem certs/server.crt
sudo cp /etc/letsencrypt/live/domain.com/privkey.pem certs/server.key
sudo chmod 600 certs/server.key
```

---

## 5. Build & Start

```bash
# Build image
docker compose build

# Start semua services
docker compose up -d

# Cek status
docker compose ps
docker compose logs -f web  # lihat log app
```

---

## 6. Verifikasi

```bash
# Cek semua container running
docker compose ps

# Expected output:
# bbm_mariadb    running (healthy)
# bbm_web        running
# bbm_nginx      running
# bbm_redis      running
# bbm_backup     running

# Test HTTP → HTTPS redirect
curl -I http://localhost

# Test app
curl -sk https://localhost/api/auth/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","pin":"123456"}'
```

---

## 7. Migrate Data (Opsional)

### Migrate Overtime Driver dari Google Sheet
```bash
docker compose exec web python3 scripts/migrate_overtime_driver.py "GOOGLE_SHEET_CSV_URL"
```

### Migrate Overtime OB/Security dari Google Sheet
```bash
docker compose exec web python3 scripts/migrate_overtime_ob_security.py "GOOGLE_SHEET_CSV_URL"
```

### Migrate Aset dari SQLite lama
```bash
docker compose exec web python3 scripts/migrate_asset_system.py /path/to/bpf_ac_ai_system.db
```

### Migrate Applicants dari Google Sheet
```bash
docker compose exec web python3 scripts/migrate_applicants_sheet.py /path/to/export.csv
```

---

## 8. Backup & Restore

### Backup sudah otomatis (cron 03:00 WIB)
```bash
# Manual backup
docker compose exec web mysqldump -ubpf_user -pbpf_pass bpf_asset_system > backup_$(date +%Y%m%d).sql

# Restore
docker compose exec -T db mysql -ubpf_user -pbpf_pass bpf_asset_system < backup.sql
```

---

## 9. Update / Redeploy

```bash
# Pull latest code
git pull

# Rebuild & restart
docker compose build --no-cache
docker compose up -d

# Install new Python dependencies (jika ada)
docker compose exec web pip install -r requirements.txt
```

---

## 10. Troubleshooting

### App tidak bisa connect ke DB
```bash
docker compose logs db | tail -20
# Pastikan healthcheck passing
docker compose exec db mysqladmin ping -h localhost -u bpf_user -pbpf_pass
```

### Port 5000 sudah terpakai
```bash
# Cek apa yang menggunakan port
sudo lsof -i :5000
# Ubah port di docker-compose.yml: "5002:5000"
```

### Font error di PDF
```bash
# Pastikan fonts ada
docker compose exec web ls -la /app/fonts/
# Jika tidak ada, rebuild: docker compose build --no-cache
```

### WebSocket tidak connect
```bash
# Pastikan nginx config support WebSocket
# Cek /socket.io di nginx.conf sudah benar
```

---

## Port Mapping

| Port | Service | Akses |
|------|---------|-------|
| 80 | Nginx HTTP | Redirect ke HTTPS |
| 443 | Nginx HTTPS | Akses utama |
| 5001 | Flask direct | HTTP only (dev) |
| 3307 | MariaDB | Host only (DB admin) |

---

## Default Accounts

| Role | Username | PIN |
|------|----------|-----|
| Admin | admin | 123456 |
| GA | ga_officer | 123456 |
| Finance | finance_officer | 123456 |
| IT Surabaya | it_ef | 123456 |

---

*BPF WorkHub v2.23.0 — Deployment Guide*
