#!/bin/bash
# ============================================================
#  TITAN OMNISCALE X v16 - VPS Deployment Script
#  Phase 3: Bare Metal Deployment (systemd + PostgreSQL)
#
#  This script sets up a production VPS from scratch:
#  1. Installs system dependencies
#  2. Creates titan user
#  3. Sets up PostgreSQL database
#  4. Creates Python virtualenv
#  5. Installs the application
#  6. Configures systemd service
#  7. Sets up Nginx reverse proxy
#  8. Obtains SSL certificate via Let's Encrypt
#
#  Usage:
#    sudo bash deploy/scripts/deploy-vps.sh
#    sudo bash deploy/scripts/deploy-vps.sh --skip-ssl
#
#  Prerequisites:
#    - Ubuntu 22.04+ or Debian 12+
#    - Root access
#    - Domain DNS pointed to this VPS
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
INSTALL_DIR="/opt/titan-omniscale"
TITAN_USER="titan"
SKIP_SSL=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --skip-ssl) SKIP_SSL=true ;;
        --help)
            echo "Usage: sudo bash deploy/scripts/deploy-vps.sh [--skip-ssl]"
            exit 0
            ;;
    esac
done

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  TITAN OMNISCALE X v16 - VPS Deployment                ║"
echo "║  Phase 3: Production Setup                              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo)"
    exit 1
fi

# ── Step 1: System Dependencies ────────────────────────────
echo "[1/8] Installing system dependencies..."
apt-get update
apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3-pip \
    postgresql-16 \
    nginx \
    certbot python3-certbot-nginx \
    curl git build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
echo "  ✓ System dependencies installed"

# ── Step 2: Create User ────────────────────────────────────
echo "[2/8] Creating titan user..."
if ! id -u ${TITAN_USER} &>/dev/null; then
    useradd -r -m -d /home/${TITAN_USER} -s /bin/bash ${TITAN_USER}
    mkdir -p /home/${TITAN_USER}/.titan_omniscale/data
    chown -R ${TITAN_USER}:${TITAN_USER} /home/${TITAN_USER}/.titan_omniscale
fi
echo "  ✓ User ${TITAN_USER} created"

# ── Step 3: PostgreSQL Setup ───────────────────────────────
echo "[3/8] Setting up PostgreSQL..."
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
sudo -u postgres psql -c "CREATE USER titan WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE titan_db OWNER titan;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE titan_db TO titan;" 2>/dev/null || true
echo "  ✓ PostgreSQL database created with random password"

# ── Step 4: Copy Application ──────────────────────────────
echo "[4/8] Installing application..."
mkdir -p ${INSTALL_DIR}
cp -r ${PROJECT_DIR}/* ${INSTALL_DIR}/
chown -R ${TITAN_USER}:${TITAN_USER} ${INSTALL_DIR}
echo "  ✓ Application copied to ${INSTALL_DIR}"

# ── Step 5: Python Virtualenv ──────────────────────────────
echo "[5/8] Creating Python virtual environment..."
sudo -u ${TITAN_USER} python3.12 -m venv ${INSTALL_DIR}/venv
sudo -u ${TITAN_USER} ${INSTALL_DIR}/venv/bin/pip install --upgrade pip
sudo -u ${TITAN_USER} ${INSTALL_DIR}/venv/bin/pip install ${INSTALL_DIR}/
sudo -u ${TITAN_USER} ${INSTALL_DIR}/venv/bin/pip install \
    "gunicorn>=21.2.0" \
    "psycopg2-binary>=2.9.9" \
    "asyncpg>=0.29.0"
echo "  ✓ Python dependencies installed"

# ── Step 6: Systemd Service ────────────────────────────────
echo "[6/8] Configuring systemd service..."
mkdir -p /var/log/titan
chown ${TITAN_USER}:${TITAN_USER} /var/log/titan

# Generate .env if not present
if [ ! -f ${INSTALL_DIR}/.env ]; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    cat > ${INSTALL_DIR}/.env << EOF
TITAN_ENV=production
TITAN_SERVER_MODE=fastapi
TITAN_AUTH_ENABLED=true
DATABASE_URL=postgresql+asyncpg://titan:${DB_PASSWORD}@localhost:5432/titan_db
DATABASE_URL_SYNC=postgresql+psycopg2://titan:${DB_PASSWORD}@localhost:5432/titan_db
TITAN_AUTH_SECRET=${SECRET}
TITAN_RAM_LIMIT_MB=4096
TITAN_WORKERS=4
LOG_LEVEL=info
EOF
    chown ${TITAN_USER}:${TITAN_USER} ${INSTALL_DIR}/.env
    chmod 600 ${INSTALL_DIR}/.env
    echo "  ✓ .env generated with random passwords"
fi

cp ${INSTALL_DIR}/deploy/systemd/titan-omniscale.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable titan-omniscale
echo "  ✓ Systemd service configured"

# ── Step 7: Nginx ──────────────────────────────────────────
echo "[7/8] Configuring Nginx..."
cp ${INSTALL_DIR}/deploy/nginx/nginx.conf /etc/nginx/nginx.conf
cp ${INSTALL_DIR}/deploy/nginx/conf.d/titan.conf /etc/nginx/conf.d/titan.conf
nginx -t
systemctl enable nginx
systemctl restart nginx
echo "  ✓ Nginx configured"

# ── Step 8: SSL ────────────────────────────────────────────
if [ "${SKIP_SSL}" = false ]; then
    echo "[8/8] Obtaining SSL certificate..."
    read -p "  Enter your domain name (e.g. api.yourdomain.com): " DOMAIN
    read -p "  Enter your email for Let's Encrypt: " EMAIL
    if [ -n "${DOMAIN}" ] && [ -n "${EMAIL}" ]; then
        certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos --email "${EMAIL}"
        echo "  ✓ SSL certificate obtained for ${DOMAIN}"
    else
        echo "  ⚠ Skipping SSL (no domain/email provided)"
    fi
else
    echo "[8/8] Skipping SSL (--skip-ssl flag)"
fi

# ── Start the service ──────────────────────────────────────
echo ""
echo "Starting TITAN OMNISCALE X..."
systemctl start titan-omniscale

# Wait and check
sleep 3
if systemctl is-active --quiet titan-omniscale; then
    echo "  ✓ Service is running!"
else
    echo "  ✗ Service failed to start. Check logs:"
    echo "    journalctl -u titan-omniscale -n 50"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  DEPLOYMENT COMPLETE                                    ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  Application:  http://localhost:5000                     ║"
echo "║  Nginx proxy:  http://localhost:80                       ║"
echo "║  API docs:     http://localhost/docs                     ║"
echo "║                                                          ║"
echo "║  IMPORTANT:                                              ║"
echo "║  1. Change default passwords in ${INSTALL_DIR}/.env       ║"
echo "║  2. Change PostgreSQL password                          ║"
echo "║  3. Set up backups: crontab -e                          ║"
echo "║     0 2 * * * pg_dump -U titan titan_db | gzip > /var/backups/titan_db_$(date+\%F).sql.gz ║"
echo "║                                                          ║"
echo "║  Commands:                                               ║"
echo "║    systemctl status titan-omniscale                      ║"
echo "║    systemctl restart titan-omniscale                     ║"
echo "║    journalctl -u titan-omniscale -f                      ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
