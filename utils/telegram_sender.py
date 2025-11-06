import os
import html
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

API_BASE = "https://api.telegram.org"
MESSAGE_LIMIT = 4096
CAPTION_LIMIT = 1024  # typical safe limit for captions


def _split_for_telegram(text: str, limit: int) -> list[str]:
    """
    Split text into chunks <= limit, preferring paragraph and line boundaries,
    with a final word-split fallback. Returns a list of chunks.
    """
    if text is None:
        return [""]
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    current: list[str] = []
    cur_len = 0

    # 1) try paragraphs
    for para in text.split("\n\n"):
        chunk = para + "\n\n"
        if cur_len + len(chunk) <= limit:
            current.append(chunk)
            cur_len += len(chunk)
        else:
            # flush current
            if current:
                parts.append("".join(current).rstrip())
                current, cur_len = [], 0

            # paragraph too big -> split by lines
            if len(chunk) > limit:
                for line in chunk.split("\n"):
                    line_n = line + "\n"
                    # line still too big -> word split
                    if len(line_n) > limit:
                        words = line_n.split(" ")
                        buf, L = [], 0
                        for w in words:
                            w2 = w + " "
                            if L + len(w2) <= limit:
                                buf.append(w2); L += len(w2)
                            else:
                                parts.append("".join(buf).rstrip())
                                buf, L = [w2], len(w2)
                        if buf:
                            parts.append("".join(buf).rstrip())
                    else:
                        if cur_len + len(line_n) <= limit:
                            current.append(line_n)
                            cur_len += len(line_n)
                        else:
                            parts.append("".join(current).rstrip())
                            current, cur_len = [line_n], len(line_n)
            else:
                current = [chunk]
                cur_len = len(chunk)

    if current:
        parts.append("".join(current).rstrip())

    # safety trim in case of edge cases
    return [p[:limit] for p in parts]


def send_telegram_message_html(translated_text: str,
                               exchange_name: str | None = None,
                               referral_link: str | None = None):
    """
    Sends a (possibly long) HTML-escaped message to TELEGRAM_CHAT_ID.
    Automatically splits into 4096-safe chunks.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment.")
        return []

    # Escape to avoid broken HTML; safe to split because no tags remain
    safe_text = html.escape(translated_text or "")

    url = f"{API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = _split_for_telegram(safe_text, MESSAGE_LIMIT)

    results = []
    for i, chunk in enumerate(chunks, 1):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",               # safe because we escaped
            "disable_web_page_preview": False,  # keep your original behavior
        }
        try:
            r = requests.post(url, json=payload, timeout=20)
            results.append(r.json())
            if r.ok and r.json().get("ok"):
                print(f"✅ Telegram message part {i}/{len(chunks)} sent (len={len(chunk)}).")
            else:
                print(f"❌ Telegram send error part {i}/{len(chunks)} (len={len(chunk)}): {r.text}")
        except Exception as e:
            print(f"❌ Telegram send exception part {i}/{len(chunks)}: {e}")

    return results


def send_photo_to_telegram_channel(image_path: str,
                                   translated_caption: str,
                                   exchange_name: str | None = None,
                                   referral_link: str | None = None):
    """
    Sends a photo with caption (<=1024 chars). If caption is longer,
    sends the remainder as follow-up 4096-safe text messages.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment.")
        return None

    # Escape caption for HTML mode
    safe_caption = html.escape(translated_caption or "")
    caption_head = safe_caption[:CAPTION_LIMIT]
    caption_tail = safe_caption[CAPTION_LIMIT:]  # send as text if present

    url = f"{API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    try:
        with open(image_path, "rb") as photo_file:
            files = {"photo": photo_file}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption_head,
                "parse_mode": "HTML",
            }
            r = requests.post(url, data=data, files=files, timeout=30)

        if r.ok and r.json().get("ok"):
            print(f"✅ Photo sent. Caption len={len(caption_head)}.")
        else:
            print(f"❌ Failed to send photo: {r.text}")

        # If remaining caption text exists, send it as regular messages
        if caption_tail:
            print(f"[INFO] Sending caption remainder as text (len={len(caption_tail)}).")
            send_telegram_message_html(caption_tail, exchange_name=exchange_name, referral_link=referral_link)

        return r.json()
    except FileNotFoundError:
        print(f"❌ Image not found: {image_path}")
    except Exception as e:
        print(f"❌ Telegram photo send exception: {e}")

    return None
