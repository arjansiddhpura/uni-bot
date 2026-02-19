# Uni-Bot — University Email → Telegram Forwarder

A lightweight Docker container that monitors your Heidelberg University email inbox and instantly forwards new messages to your Telegram chat.

**How it works:** The bot connects to the university VPN (Cisco AnyConnect), opens an IMAP IDLE connection to the mail server, and the moment a new email arrives it sends you a Telegram message with the sender, subject, and body.

---

## Prerequisites

| Requirement | Why |
|---|---|
| A Linux VPS (e.g. Hetzner, DigitalOcean) | Runs the bot 24/7 |
| [Docker](https://docs.docker.com/engine/install/) installed | Containerises everything |
| A Heidelberg University account | VPN + email access |
| TOTP secret for university 2FA | The *base32 seed*, not the 6-digit code |
| A Telegram bot token + your chat ID | Where notifications are sent |

---

## 1 — Create a Telegram Bot

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts to choose a name.
3. BotFather will give you a **bot token** — save it (looks like `123456:ABC-DEF...`).
4. To find your **chat ID**, search for **@userinfobot** and send it any message. It will reply with your numeric ID.

## 2 — Get Your TOTP Secret

Your university account uses two-factor authentication. You need the **base32 secret key** (the seed), not the 6-digit code that changes every 30 seconds.

- If you set up 2FA with an authenticator app, you likely received a QR code or a text secret like `JBSWY3DPEHPK3PXP`. That's the value you need.
- If you only have the QR code, scan it — the URL inside looks like `otpauth://totp/...?secret=JBSWY3DPEHPK3PXP`. Copy the `secret=` part.

## 3 — Clone & Configure

```bash
git clone <your-repo-url> uni-bot
cd uni-bot
```

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
nano .env          # or use any text editor
```

Fill in every value:

```dotenv
# VPN (Cisco AnyConnect)
VPN_USER=ab123                  # your Uni-ID
VPN_PASSWORD=your-vpn-password
TOTP_SECRET=JBSWY3DPEHPK3PXP   # base32 secret (NOT the 6-digit code)

# IMAP
IMAP_HOST=imap.urz.uni-heidelberg.de
IMAP_PORT=993
EMAIL_USER=ab123                # usually same as VPN_USER
EMAIL_PASS=your-email-password

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=123456789
```

> **Tip:** Keep `.env` private. It is already listed in `.gitignore` so it won't be committed.

## 4 — Start the Bot

```bash
sudo docker compose up --build -d
```

This builds the image (takes ~30 s the first time) and starts the container in the background.

## 5 — Check That It's Running

```bash
sudo docker logs uni-bot
```

You should see output like:

```
[entrypoint] Starting openconnect VPN …
[entrypoint] Authenticating …
[entrypoint] Connecting tunnel to https://vpnsrv2.urz.uni-heidelberg.de/ …
[entrypoint] VPN tunnel up
2026-02-19 16:52:08  INFO     Bot started — last UID = 4855
2026-02-19 16:52:08  INFO     IMAP connected
```

And you'll receive a Telegram message: **✅ Uni-Bot started — Listening for new emails …**

---

## Common Commands

| Action | Command |
|---|---|
| View logs | `sudo docker logs -f uni-bot` |
| Restart | `sudo docker compose restart` |
| Stop | `sudo docker compose down` |
| Rebuild after code changes | `sudo docker compose up --build -d` |
| Check resource usage | `sudo docker stats uni-bot --no-stream` |

---

## How It Works (Under the Hood)

```
┌──────────────┐     VPN tunnel       ┌────────────────────┐
│  Your VPS    │◄────────────────────►│  Uni Heidelberg    │
│              │   (openconnect)      │  VPN Gateway       │
│  ┌────────┐  │                      └────────────────────┘
│  │ uni-bot│  │     IMAP IDLE        ┌────────────────────┐
│  │        │──┼─────────────────────►│  imap.urz.uni-     │
│  └───┬────┘  │                      │  heidelberg.de:993 │
│      │       │                      └────────────────────┘
└──────┼───────┘
       │  HTTPS
       ▼
┌──────────────┐
│  Telegram    │
│  Bot API     │
└──────────────┘
```

1. **VPN** — `entrypoint.sh` authenticates with username + password + TOTP, then opens a tunnel via `openconnect`.
2. **IMAP IDLE** — `bot.py` holds a persistent connection to the mail server. The server *pushes* a notification the instant a new email arrives (no polling).
3. **Telegram** — The bot formats the email (sender, subject, body) and sends it to your chat.
4. **UID tracking** — Each email's UID is saved to disk so the bot never sends duplicates, even after a restart.

---

## Resource Usage

The container is extremely lightweight:

- **RAM:** ~21 MiB
- **CPU:** 0%
- **Processes:** 3 (shell + openconnect + python)

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `Authentication failed` in logs | Double-check `VPN_USER`, `VPN_PASSWORD`, and `TOTP_SECRET` in `.env`. Make sure `TOTP_SECRET` is the base32 seed, not a 6-digit code. |
| `tun0 did not come up within 45s` | The VPN server may be temporarily unavailable. The container will auto-restart and retry. |
| No Telegram message received | Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Make sure you've sent at least one message to your bot first (Telegram requires this). |
| `IMAP login failed` | Check `EMAIL_USER` and `EMAIL_PASS`. These may differ from your VPN credentials. |
| Container keeps restarting | Run `sudo docker logs uni-bot` to see the error. Most issues are credential-related. |

---

## License

MIT
