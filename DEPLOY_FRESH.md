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

## 4. Pilih Skenario HTTPS

### Skenario A: Server Hybrid (Nextcloud + BPF) ⭐ RECOMMENDED

Jika server juga menjalankan Nextcloud (sama seperti production saat ini):

```bash
# 1. Clone hybrid_nextcloud (jika belum ada)
cd /home/$USER
git clone https://github.com/bestprofitsurabaya/hybrid_nextcloud.git
cd hybrid_nextcloud

# 2. Jalankan Nextcloud dulu
docker compose up -d

# 3. Pastikan network nextcloud_net ada
docker network ls | grep nextcloud_net

# 4. Copy config nginx untuk BPF
cp ~/bpf-workhub/nginx/bbm_system.conf ~/hybrid_nextcloud/nginx/conf.d/

# 5. Restart nginx
docker restart nextcloud_nginx

# 6. Kembali ke bpf-workhub
cd ~/bpf-workhub

# 7. Build & Start
docker compose build
docker compose up -d
```

**Port mapping (Skenario A):**
| Port | Service | Akses |
|------|---------|-------|
| 443 | Nextcloud HTTPS | nextcloud.domain.com |
| 5000 | BPF via nextcloud_nginx | domain.com:5000 |
| 3307 | MariaDB | Host only |

### Skenario B: Server Dedicated (BPF saja)

Jika server hanya untuk BPF WorkHub tanpa Nextcloud:

```bash
# 1. Generate SSL certificate
# Self-signed (development):
bash scripts/gen-selfsigned-cert.sh

# Atau Let's Encrypt (production):
sudo apt install -y certbot
sudo certbot certonly --standalone -d your-domain.com
mkdir -p certs
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem certs/server.crt
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem certs/server.key
sudo chmod 600 certs/server.key

# 2. Build & Start (dengan nginx standalone)
docker compose --profile standalone-nginx build
docker compose --profile standalone-nginx up -d

# Atau tanpa profile (hanya web + db + redis):
docker compose build
docker compose up -d
# Akses via: http://your-server-ip:5001
```

---

## 5. Verifikasi

```bash
# Cek semua container running
docker compose ps

# Skenario A (hybrid):
# bbm_mariadb    running (healthy)
# bbm_web        running
# bbm_redis      running
# bbm_backup     running
# (+ nextcloud_* containers dari hybrid_nextcloud)

# Skenario B (dedicated):
# bbm_mariadb    running (healthy)
# bbm_web        running
# bbm_nginx      running
# bbm_redis      running
# bbm_backup     running

# Test login
curl -sk https://your-server:5000/api/auth/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","pin":"123456"}'
```

---

## 6. Migrate Data (Opsional)

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

## 7. Backup & Restore

### Backup sudah otomatis (cron 03:00 WIB)
```bash
# Manual backup
docker compose exec web mysqldump -ubpf_user -pbpf_pass bpf_asset_system > backup_$(date +%Y%m%d).sql

# Restore
docker compose exec -T db mysql -ubpf_user -pbpf_pass bpf_asset_system < backup.sql
```

---

## 8. Update / Redeploy

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

## 9. Troubleshooting

### App tidak bisa connect ke DB
```bash
docker compose logs db | tail -20
docker compose exec db mysqladmin ping -h localhost -u bpf_user -pbpf_pass
```

### Port 5000 sudah terpakai
```bash
sudo lsof -i :5000
# Ubah port di docker-compose.yml: "5002:5000"
```

### Font error di PDF
```bash
docker compose exec web ls -la /app/fonts/
# Jika tidak ada: docker compose build --no-cache
```

### WebSocket tidak connect
```bash
# Pastikan nginx config support WebSocket
# Di bbm_system.conf harus ada:
#   proxy_set_header Upgrade $http_upgrade;
#   proxy_set_header Connection "upgrade";
```

### nextcloud_net network not found (Skenario A)
```bash
# Pastikan Nextcloud sudah running
cd ~/hybrid_nextcloud && docker compose up -d
docker network ls | grep nextcloud_net
```

---

## Default Accounts

| Role | Username | PIN |
|------|----------|-----|
| Admin | admin | 123456 |
| GA | ga_officer | 123456 |
| Finance | finance_officer | 123456 |
| IT Surabaya | it_sby | 123456 |
| IT Jakarta HO | it_hu | 123456 |
| IT Jakarta 2 | it_jkt2 | 123456 |
| IT Bandung | it_bdg | 123456 |
| IT Semarang | it_smg | 123456 |
| IT Malang | it_mlg | 123456 |
| IT Medan | it_mdn | 123456 |
| IT Banjarmasin | it_bjm | 123456 |
| IT Palembang | it_plm | 123456 |
| IT Lampung | it_lpg | 123456 |

---

*BPF WorkHub v2.28.0 — Deployment Guide*
