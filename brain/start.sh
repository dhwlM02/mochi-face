#!/bin/bash
# Starts Mochi's brain on this Mac: checks Ollama, makes the HTTPS certificate
# the phone needs (camera + microphone only work over HTTPS), then runs server.py.
cd "$(dirname "$0")" || exit 1
PORT="${MOCHI_PORT:-8765}"

echo ""
echo "  Waking up Mochi's brain..."

# 1. Ollama
if ! command -v ollama >/dev/null 2>&1; then
  echo "  Ollama isn't installed. Download it from https://ollama.com/download, open it once, then run ./start.sh again."
  exit 1
fi
if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "  Starting Ollama..."
  open -a Ollama 2>/dev/null || (ollama serve >/tmp/ollama.log 2>&1 &)
  for i in $(seq 1 30); do curl -s http://127.0.0.1:11434/api/tags >/dev/null && break; sleep 1; done
fi
if [ -z "$MOCHI_MODEL" ] && [ -z "$(ollama list 2>/dev/null | tail -n +2 | grep -v embed)" ]; then
  echo "  No chat model found. Downloading llama3.2:3b (about 2 GB, one time only)..."
  ollama pull llama3.2:3b || exit 1
fi

# 2. HTTPS certificate for this Mac's Wi-Fi address
IP="$(ipconfig getifaddr en0 2>/dev/null)"
[ -z "$IP" ] && IP="$(ipconfig getifaddr en1 2>/dev/null)"
[ -z "$IP" ] && IP="127.0.0.1"
if [ ! -f cert.pem ] || [ ! -f key.pem ] || [ "$(cat .cert-ip 2>/dev/null)" != "$IP" ]; then
  echo "  Making a certificate for $IP..."
  cat > .openssl.cnf <<EOF
[req]
distinguished_name = dn
x509_extensions = v3
prompt = no
[dn]
CN = Mochi Brain
[v3]
subjectAltName = IP:$IP,IP:127.0.0.1,DNS:localhost
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
EOF
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 -keyout key.pem -out cert.pem -config .openssl.cnf >/dev/null 2>&1 \
    || { echo "  Couldn't make the certificate (openssl failed)."; exit 1; }
  echo "$IP" > .cert-ip
fi

# 3. Run
exec python3 server.py
