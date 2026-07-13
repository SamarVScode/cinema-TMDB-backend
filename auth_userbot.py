import asyncio
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from dotenv import load_dotenv
from utils.logger import setup_logger

load_dotenv()
logger = setup_logger("auth")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "relay_userbot")

async def main():
    if not API_ID or not API_HASH:
        logger.error("Please set API_ID and API_HASH in your .env file.")
        return

    logger.info("Authenticating Telethon Userbot...")
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        phone = input("Enter your secondary phone number (with country code): ")
        await client.send_code_request(phone)
        code = input("Enter the code you received: ")
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input("Two-step verification is enabled. Enter your password: ")
            await client.sign_in(password=password)
    
    logger.info("Authentication successful!")
    logger.info(f"Session saved as: {SESSION_NAME}.session")
    
    me = await client.get_me()
    logger.info(f"Logged in as: {me.first_name} (@{me.username})")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
