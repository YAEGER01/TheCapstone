#!/usr/bin/env bash
# Provision Let's Encrypt TLS on the PRODUCTION Linux server.
# Run ONCE on the server as root (not from Windows dev):
#
#   sudo bash deploy/enable_prod_tls.sh admin@isucaufa-fms.online
#
# What it does:
#   1. installs certbot (snap or apt) + nginx plugin
#   2. issues certs for isucaufa-fms.online + www (HTTP-01 via nginx)
#   3. installs deploy/nginx.prod.conf
#   4. installs a weekly renewal cron with --deploy-hook "nginx -s reload"
#   5. verifies: 443 serves the chain, http->https redirects, HSTS present
set -euo pipefail

EMAIL="${1:?usage: sudo bash deploy/enable_prod_tls.sh admin@example.com}"
DOMAIN="isucaufa-fms.online"
WWW="www.isucaufa-fms.online"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/6] Installing certbot..."
if command -v snap >/dev/null 2>&1; then
  snap install core 2>/dev/null || true
  snap refresh core 2>/dev/null || true
  snap install --classic certbot 2>/dev/null || true
  ln -sf /snap/bin/certbot /usr/bin/certbot
else
  apt-get update -y
  apt-get install -y certbot python3-certbot-nginx
fi
command -v nginx >/dev/null || apt-get install -y nginx

echo "[2/6] Issuing certificate for $DOMAIN + $WWW ..."
mkdir -p /var/www/certbot
certbot certonly --nginx --non-interactive --agree-tos \
  --email "$EMAIL" --no-eff-email \
  -d "$DOMAIN" -d "$WWW" \
  --webroot-path /var/www/certbot || \
certbot --nginx --non-interactive --agree-tos \
  --email "$EMAIL" --no-eff-email \
  -d "$DOMAIN" -d "$WWW"

echo "[3/6] Installing production nginx config..."
cp /etc/nginx/nginx.conf "/etc/nginx/nginx.conf.bak.$(date +%Y%m%d%H%M%S)"
cp "$SCRIPT_DIR/nginx.prod.conf" /etc/nginx/nginx.conf
nginx -t
systemctl reload nginx 2>/dev/null || nginx -s reload

echo "[4/6] Installing weekly renewal cron (certbot timer is primary)..."
CRON_FILE="/etc/cron.d/caufa-certbot-renew"
cat > "$CRON_FILE" <<'EOF'
# CAUFASYSTEM: backstop TLS renewal (certbot's systemd timer is primary).
# Runs weekly; reloads nginx only when a cert actually renewed.
17 3 * * 1 root certbot renew --quiet --deploy-hook "nginx -s reload"
EOF
chmod 644 "$CRON_FILE"

echo "[5/6] Forcing one dry-run renewal to prove the pipeline..."
certbot renew --dry-run --quiet

echo "[6/6] Verifying live TLS..."
echo "--- 443 chain ---"
echo | openssl s_client -connect "$DOMAIN:443" -servername "$DOMAIN" 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
echo "--- http -> https redirect ---"
curl -sI "http://$DOMAIN/" | head -n 3
echo "--- HSTS header ---"
curl -sI "https://$DOMAIN/" | grep -i strict-transport || {
  echo "!! HSTS header missing — check config before preload submission"; exit 1;
}
echo
echo "OK. Next: set APP_ENV=production in the server .env, then run"
echo "scripts/check_hsts_preload.ps1 from dev to confirm preload eligibility."
