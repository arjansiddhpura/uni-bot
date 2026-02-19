"""Heidelberg Uni-Mail → Telegram forwarder via IMAP IDLE."""

import html
import logging
import os
import socket
import sys
import time
import imaplib
from pathlib import Path

import requests
from imap_tools import MailBox, AND, MailboxLoginError, MailboxLogoutError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IMAP_HOST = os.environ["IMAP_HOST"]
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]

TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT  = os.environ["TELEGRAM_CHAT_ID"]

UID_FILE = Path(os.environ.get("UID_FILE", "/data/last_uid.txt"))

IDLE_TIMEOUT   = 180        # seconds per IDLE cycle (3 min)
MAX_CONN_TIME  = 29 * 60    # reconnect IMAP every 29 min (RFC 2177)
RECONNECT_WAIT = 60         # seconds to wait before retrying after error
MAX_BODY_LEN   = 3800       # Telegram message limit safety (~4096 chars)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("uni-bot")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tg_send(text: str) -> None:
    """Send a message to Telegram with retry on transient errors."""
    text = text[:4096]
    for attempt in range(1, 4):  # up to 3 attempts
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"},
                timeout=15,
            )
            if r.ok:
                return
            log.warning("Telegram API %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            log.warning("Telegram send failed (attempt %d/3): %s", attempt, e)
        if attempt < 3:
            time.sleep(2 ** attempt)  # 2s, 4s
    log.error("Telegram send gave up after 3 attempts")


def read_last_uid() -> int:
    """Read the persisted UID, or 0 if not yet stored."""
    try:
        return int(UID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def write_last_uid(uid: int) -> None:
    UID_FILE.parent.mkdir(parents=True, exist_ok=True)
    UID_FILE.write_text(str(uid))


def escape(s: str) -> str:
    return html.escape(s or "")


def format_email(sender: str, subject: str, body: str) -> str:
    body = (body or "").strip()
    if len(body) > MAX_BODY_LEN:
        body = body[:MAX_BODY_LEN] + "\n… [truncated]"
    return (
        f"<b>From:</b> {escape(sender)}\n"
        f"<b>Subject:</b> {escape(subject)}\n\n"
        f"<pre>{escape(body)}</pre>"
    )

# ---------------------------------------------------------------------------
# Seed UID on first run
# ---------------------------------------------------------------------------

def seed_uid() -> int:
    """Connect once, grab the highest UID in inbox, persist it, and return it.
    This ensures old mail is never forwarded on first launch."""
    log.info("Seeding last UID from current inbox state …")
    with MailBox(IMAP_HOST, IMAP_PORT).login(EMAIL_USER, EMAIL_PASS, "INBOX") as mb:
        uids = [int(m.uid) for m in mb.fetch(AND(all=True), headers_only=True, bulk=True)]
        max_uid = max(uids) if uids else 0
    write_last_uid(max_uid)
    log.info("Seeded last UID = %d", max_uid)
    return max_uid

# ---------------------------------------------------------------------------
# Main IDLE loop
# ---------------------------------------------------------------------------

def run() -> None:
    last_uid = read_last_uid()
    if last_uid == 0:
        last_uid = seed_uid()

    log.info("Bot started — last UID = %d", last_uid)
    startup_notified = False

    while True:
        conn_start = time.monotonic()
        conn_age = 0.0
        try:
            with MailBox(IMAP_HOST, IMAP_PORT).login(EMAIL_USER, EMAIL_PASS, "INBOX") as mb:
                log.info("IMAP connected")
                if not startup_notified:
                    tg_send("<b>Uni-Bot started</b>\nListening for new emails\u2026")
                    startup_notified = True
                # Catch-up fetch: grab any emails that arrived during reconnect gap
                criteria = AND(uid=f"{last_uid + 1}:*")
                for msg in mb.fetch(criteria, mark_seen=False):
                    uid = int(msg.uid)
                    if uid <= last_uid:
                        continue
                    log.info("Catch-up email UID=%d from=%s subj=%s", uid, msg.from_, msg.subject)
                    tg_send(format_email(msg.from_, msg.subject, msg.text))
                    if uid > last_uid:
                        last_uid = uid
                        write_last_uid(last_uid)

                while conn_age < MAX_CONN_TIME:
                    try:
                        responses = mb.idle.wait(timeout=IDLE_TIMEOUT)
                    except KeyboardInterrupt:
                        log.info("Interrupted — shutting down")
                        return

                    if responses:
                        log.info("IDLE response: %s", responses)
                        # Fetch messages with UID greater than our bookmark
                        criteria = AND(uid=f"{last_uid + 1}:*")
                        for msg in mb.fetch(criteria, mark_seen=False):
                            uid = int(msg.uid)
                            if uid <= last_uid:
                                continue
                            log.info("New email UID=%d from=%s subj=%s", uid, msg.from_, msg.subject)
                            tg_send(format_email(msg.from_, msg.subject, msg.text))
                            if uid > last_uid:
                                last_uid = uid
                                write_last_uid(last_uid)

                    conn_age = time.monotonic() - conn_start

                log.info("29-min reconnect cycle — refreshing IMAP session")

        except KeyboardInterrupt:
            log.info("Interrupted — shutting down")
            return
        except (
            TimeoutError,
            ConnectionError,
            OSError,
            imaplib.IMAP4.abort,
            MailboxLoginError,
            MailboxLogoutError,
            socket.herror,
            socket.gaierror,
            socket.timeout,
        ) as exc:
            log.warning("Connection error: %s — retrying in %ds", exc, RECONNECT_WAIT)
            time.sleep(RECONNECT_WAIT)
        except Exception as exc:
            log.exception("Unexpected error: %s — retrying in %ds", exc, RECONNECT_WAIT)
            time.sleep(RECONNECT_WAIT)


if __name__ == "__main__":
    run()
