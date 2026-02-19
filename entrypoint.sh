#!/bin/sh

# ── VPN Connect (two-step: authenticate → tunnel) ────────────────────────────
echo "[entrypoint] Starting openconnect VPN …"

# Generate TOTP code right before connecting (time-sensitive)
OTP_CODE=$(python3 -c "import pyotp; print(pyotp.TOTP('${TOTP_SECRET}').now())")

# Step 1: Authenticate — get session cookie
# --no-external-auth: workaround for v9.12 STRAP/TLS1.3 bug (gitlab.com/openconnect/openconnect/-/issues/773)
echo "[entrypoint] Authenticating …"
AUTH_OUTPUT=$(printf '%s\n%s\n' "$VPN_PASSWORD" "$OTP_CODE" | openconnect \
    --user="$VPN_USER" \
    --passwd-on-stdin \
    --non-inter \
    --protocol=anyconnect \
    --useragent='AnyConnect' \
    --no-external-auth \
    --authenticate \
    vpn-ac.urz.uni-heidelberg.de 2>&1)

if [ $? -ne 0 ]; then
    echo "[entrypoint] Authentication failed:"
    echo "$AUTH_OUTPUT"
    sleep 120
    exit 1
fi

eval $(echo "$AUTH_OUTPUT" | grep -E '^(COOKIE|HOST|FINGERPRINT|CONNECT_URL|RESOLVE)=')

# Step 2: Establish tunnel with session cookie
echo "[entrypoint] Connecting tunnel to $CONNECT_URL …"
echo "$COOKIE" | openconnect \
    --cookie-on-stdin \
    --servercert "$FINGERPRINT" \
    --resolve "$RESOLVE" \
    --pid-file=/run/vpn.pid \
    --protocol=anyconnect \
    --useragent='AnyConnect' \
    --no-external-auth \
    "$CONNECT_URL" &

VPN_PID=$!

# ── Wait for tunnel ──────────────────────────────────────────────────────────
echo "[entrypoint] Waiting for tun0 …"
TRIES=0
while ! ip link show tun0 >/dev/null 2>&1; do
    if ! kill -0 "$VPN_PID" 2>/dev/null; then
        echo "[entrypoint] ERROR: openconnect process died"
        sleep 60
        exit 1
    fi
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge 45 ]; then
        echo "[entrypoint] ERROR: tun0 did not come up within 45s"
        kill "$VPN_PID" 2>/dev/null
        sleep 60
        exit 1
    fi
    sleep 1
done
echo "[entrypoint] VPN tunnel up"

# ── Run bot ──────────────────────────────────────────────────────────────────
python3 /app/bot.py
echo "[entrypoint] Bot exited — cleaning up"
kill "$VPN_PID" 2>/dev/null
sleep 10
exit 1
