import os
import asyncio
import time
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from utils.logger import setup_logger
import relay

load_dotenv()
logger = setup_logger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_IDS = [int(id.strip()) for id in os.getenv("ADMIN_USER_IDS", "").split(",") if id.strip()]

start_time = time.time()
user_last_query = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Movie Bot Relay!\n"
        "Send me a movie name, and I will find the information for you."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Usage:\n"
        "Just send a movie name to get started.\n"
        "/start - Welcome message\n"
        "/help - Show this message"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_USER_IDS and user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("Unauthorized.")
        return

    stats = relay.rate_limiter.get_stats()
    uptime_seconds = int(time.time() - start_time)
    uptime_str = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m {uptime_seconds % 60}s"
    
    connection_status = "Connected" if relay.userbot_client and relay.userbot_client.is_connected() else "Disconnected"
    sleep_status = "Sleeping 💤" if stats.get("is_sleeping") else "Active 🟢"

    await update.message.reply_text(
        f"*Bot Statistics:*\n"
        f"Uptime: `{uptime_str}`\n"
        f"Userbot Connection: `{connection_status}`\n"
        f"Current State: `{sleep_status}`\n"
        f"Queries last minute: `{stats['last_minute']}`\n"
        f"Queries last hour: `{stats['last_hour']}`\n"
        f"Queries last day: `{stats['last_day']}`\n"
        f"Consecutive errors: `{stats['consecutive_errors']}`\n"
        f"Throttle multiplier: `{stats['throttle_multiplier']:.2f}x`",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    if not query:
        return
        
    user_id = update.effective_user.id
    
    # Input validation
    if len(query) < 2 or len(query) > 200:
        await update.message.reply_text("Please provide a valid movie name (between 2 and 200 characters).")
        return
        
    # Per-user cooldown
    now = time.time()
    if user_id in user_last_query and now - user_last_query[user_id] < 5:
        await update.message.reply_text("Please wait a few seconds before sending another query.", parse_mode=ParseMode.MARKDOWN)
        return
        
    user_last_query[user_id] = now
    
    logger.info(f"Received query from user {user_id}: {query}")
    
    # Send a processing message
    processing_msg = await update.message.reply_text("Searching for movie... ⏳")
    
    # Get movie info via relay
    response = await relay.get_movie_info(query)
    
    # Update the processing message with the result
    try:
        if isinstance(response, str):
            await processing_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
        elif isinstance(response, dict):
            links = response.get("embedded_links", [])
            reply_text = "Here are your results:\n\n"
            
            if not links:
                reply_text = response.get("text", "No links found.")
            else:
                for link in links:
                    url = link.get("url", "")
                    title = link.get("text", "Movie")
                    
                    if "?start=" in url:
                        parts = url.split("?start=")
                        bot_name = parts[0].split("/")[-1]
                        key = parts[1]
                        # Escaping special characters for MarkdownV2 or just using plain text
                        reply_text += f"🎬 {title}\n🤖 @{bot_name}\n🔑 `/start {key}`\n\n"
                    else:
                        reply_text += f"🎬 {title}\n🔗 {url}\n\n"
                        
            await processing_msg.edit_text(reply_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        # Fallback to plain text if markdown parsing or formatting fails
        logger.warning(f"Failed to send response correctly: {e}")
        if isinstance(response, dict):
            await processing_msg.edit_text(response.get("text", "Error rendering result."))
        else:
            await processing_msg.edit_text(response)

async def post_init(application: Application):
    # Start the relay client
    await relay.start_relay()

async def post_stop(application: Application):
    # Stop the relay client
    await relay.stop_relay()

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in .env file.")
        return

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).post_stop(post_stop).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting Telegram Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
