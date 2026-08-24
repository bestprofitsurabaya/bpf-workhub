#!/bin/bash
# Generate self-signed SSL certificate untuk development
# Untuk production: gunakan certbot/Let's Encrypt

CERT_DIR="$(dirname "$0")/../certs"
mkdir -p "$CERT_DIR"

echo "🔐 Generating self-signed SSL certificate..."

openssl req -x509 -nodes -days 365 \
  -newkey rsa:2048 \
  -keyout "$CERT_DIR/server.key" \
  -out "$CERT_DIR/server.crt" \
  -subj "/C=ID/ST=Jawa Timur/L=Surabaya/O=PT Bestprofit Futures/CN=localhost" \
  2>/dev/null

chmod 600 "$CERT_DIR/server.key"
chmod 644 "$CERT_DIR/server.crt"

echo "✅ Certificate generated:"
echo "   📁 $CERT_DIR/server.crt"
echo "   🔑 $CERT_DIR/server.key"
echo ""
echo "⚠️  Ini self-signed certificate (untuk development)."
echo "   Untuk production, gunakan Let's Encrypt:"
echo "   docker compose run --rm certbot certonly --webroot -w /var/www/certbot"
