import sys
import os
import asyncio

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient

from utils.google_sheet_reader import fetch_channels_from_google_sheet
from utils.telegram_reader import extract_channel_username, fetch_latest_messages
from utils.ai_translator import translate_text_gemini
from utils.telegram_sender import send_telegram_message_html, send_photo_to_telegram_channel
from utils.json_writer import save_results, load_posted_messages


async def main():
    telegram_api_id = os.environ['TELEGRAM_API_ID']
    telegram_api_hash = os.environ['TELEGRAM_API_HASH']
    sheet_id = os.environ['GOOGLE_SHEET_ID']
    google_sheet_api_key = os.environ['GOOGLE_SHEET_API_KEY']

    # Already-posted messages (to avoid duplicates)
    posted_messages = load_posted_messages()
    result_output = []

    # Each entry now includes: Name, Link, Type → channel_type
    channels_data = fetch_channels_from_google_sheet(sheet_id, google_sheet_api_key)

    for entry in channels_data:
        channel_link = entry["channel_link"]
        channel_type = entry.get("channel_type")  # e.g. "Alpha", "Inf0fi", "Dana Kripto"
        channel_username = extract_channel_username(channel_link)

        print(f"\n📡 Processing channel: {channel_username} (Type: {channel_type})")

        messages = await fetch_latest_messages(
            telegram_api_id,
            telegram_api_hash,
            channel_username
        )

        for msg in messages:
            # Skip if this text was already posted before
            if msg["text"] in posted_messages:
                print(f"⚠️ Skipping duplicate message ID {msg['id']} from {channel_username}")
                continue

            # Translate with Gemini (your existing function)
            translated = translate_text_gemini(msg["text"])

            if msg["has_photo"]:
                image_path = f"photo_{msg['id']}.jpg"

                # Download photo from source channel
                async with TelegramClient("telegram_session", telegram_api_id, telegram_api_hash) as client:
                    await client.download_media(msg["raw"], image_path)

                # ✅ Send photo with [Type] prefix in caption
                send_photo_to_telegram_channel(
                    image_path=image_path,
                    translated_caption=translated,
                    post_type=channel_type   # <<< IMPORTANT
                )

                # Clean up local file
                os.remove(image_path)
            else:
                # ✅ Send text-only message with [Type] prefix
                send_telegram_message_html(
                    translated_text=translated,
                    post_type=channel_type   # <<< IMPORTANT
                )

            # Log what we posted
            result_output.append({
                "channel_link": channel_link,
                "channel_type": channel_type,
                "original_text": msg["text"],
                "translated_text": translated,
                "date": msg["date"],
                "message_id": msg["id"],
            })

    if result_output:
        save_results(result_output)


if __name__ == "__main__":
    asyncio.run(main())
