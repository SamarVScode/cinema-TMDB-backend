import asyncio
import os
import random
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import ReadHistoryRequest
from utils.logger import setup_logger
from rate_limiter import RateLimiter

logger = setup_logger("relay")

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
session_name = os.getenv("SESSION_NAME", "relay_userbot")

# Comma-separated list of target bots
target_bots_str = os.getenv("THIRD_PARTY_BOT_USERNAMES", "@MovieInfoBot")
target_bots = [bot.strip() for bot in target_bots_str.split(",") if bot.strip()]

timeout = int(os.getenv("REPLY_TIMEOUT_SECONDS", 15))

userbot_client = TelegramClient(session_name, int(api_id) if api_id else 0, api_hash) if api_id and api_hash else None
rate_limiter = RateLimiter()
pending_requests = {}
_request_lock = asyncio.Lock()

async def simulate_activity():
    """Simulate random reads to appear more human."""
    try:
        # Occasionally mark the bots' chats as read
        if random.random() < 0.3:
            bot_to_read = random.choice(target_bots)
            entity = await userbot_client.get_input_entity(bot_to_read)
            await userbot_client(ReadHistoryRequest(peer=entity, max_id=0))
            logger.info(f"Simulated random read activity for {bot_to_read}.")
    except Exception as e:
        logger.warning(f"Error in activity simulation: {e}")

async def start_relay():
    if not userbot_client:
        logger.error("API_ID or API_HASH missing, cannot start relay.")
        return
        
    logger.info("Starting userbot client...")
    await userbot_client.start()
    
    @userbot_client.on(events.NewMessage(from_users=target_bots))
    async def handler(event):
        sender = await event.get_sender()
        logger.info(f"Received reply from {sender.username or sender.id}")
        reply_to_msg_id = event.message.reply_to_msg_id
        
        # Build structured response
        reply_data = {
            "sender": f"@{sender.username}" if sender and sender.username else "UnknownBot",
            "text": event.message.text,
            "embedded_links": [],
            "buttons": []
        }
        
        # Extract embedded links (TextUrl and Url)
        if event.message.entities:
            from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
            for ent, text in event.message.get_entities_text():
                if isinstance(ent, MessageEntityTextUrl):
                    reply_data["embedded_links"].append({"text": text, "url": ent.url})
                elif isinstance(ent, MessageEntityUrl):
                    reply_data["embedded_links"].append({"text": text, "url": text})
                    
        # Extract Inline Buttons (any type)
        if event.message.reply_markup and hasattr(event.message.reply_markup, 'rows'):
            for row in event.message.reply_markup.rows:
                for button in row.buttons:
                    if hasattr(button, 'text'):
                        reply_data["buttons"].append({
                            "text": button.text,
                            "url": getattr(button, 'url', None)
                        })

        async with _request_lock:
            # If the third-party bot replies to our message directly
            if reply_to_msg_id and reply_to_msg_id in pending_requests:
                req_data = pending_requests.pop(reply_to_msg_id)
                future = req_data["future"]
                if not future.done():
                    future.set_result(reply_data)
            else:
                # Fallback: resolve the oldest pending request for THIS specific bot
                sender_username = f"@{sender.username.lower()}" if getattr(sender, 'username', None) else ""
                for msg_id, req_data in list(pending_requests.items()):
                    if req_data["bot"].lower() == sender_username:
                        future = req_data["future"]
                        del pending_requests[msg_id]
                        if not future.done():
                            future.set_result(reply_data)
                        break

async def stop_relay():
    if userbot_client:
        await userbot_client.disconnect()

async def simulate_typing(query: str):
    """Simulate typing duration based on query length for all target bots."""
    typing_time = min(len(query) * 0.1, 5.0)
    
    async def _type_action(bot):
        try:
            async with userbot_client.action(bot, 'typing'):
                await asyncio.sleep(typing_time)
        except Exception as e:
            logger.warning(f"Failed to simulate typing for {bot}: {e}")
            
    await asyncio.gather(*[_type_action(bot) for bot in target_bots])

async def get_movie_info(query: str, max_retries=3) -> list:
    retries = 0
    while retries < max_retries:
        try:
            # Wait according to rate limits
            delay = await rate_limiter.wait_if_needed()
            logger.info(f"Rate limiter delayed request by {delay:.2f}s")
            
            await simulate_activity()
            await simulate_typing(query)
            
            bot_futures = {bot: asyncio.Future() for bot in target_bots}
            
            # Send the message to all target bots
            async with _request_lock:
                for bot in target_bots:
                    try:
                        sent_msg = await userbot_client.send_message(bot, query)
                        pending_requests[sent_msg.id] = {"bot": bot, "future": bot_futures[bot]}
                        logger.info(f"Sent query to {bot}: {query}")
                    except Exception as e:
                        logger.warning(f"Failed to send query to {bot}: {e}")
                        bot_futures[bot].set_result({"error": str(e)})
            
            # Wait for ALL bots to reply, with a timeout
            done, pending = await asyncio.wait(
                bot_futures.values(),
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )
            
            # Cancel any bots that timed out
            for p in pending:
                p.cancel()
                
            rate_limiter.report_success()
            
            # Aggregate all successful results
            all_responses = []
            for bot, future in bot_futures.items():
                if future.done() and not future.cancelled() and not future.exception():
                    res = future.result()
                    if "error" not in res:
                        all_responses.append(res)
            
            return all_responses
            
        except FloodWaitError as e:
            logger.error(f"FloodWaitError: Must wait {e.seconds} seconds")
            rate_limiter.report_error()
            await asyncio.sleep(e.seconds)
            retries += 1
            if retries >= max_retries:
                return [{"error": f"Telegram rate limit exceeded. Tried {max_retries} times."}]
                
        except Exception as e:
            logger.error(f"Error querying movie bots: {str(e)}")
            rate_limiter.report_error()
            return [{"error": str(e)}]
            
        finally:
            # Ensure pending requests are cleaned up
            async with _request_lock:
                to_remove = [k for k, v in pending_requests.items() if v["bot"] in target_bots]
                for k in to_remove:
                    del pending_requests[k]
                    
    return [{"error": "Maximum retries exceeded."}]

async def auto_forward_movie(query: str, bot_username: str, target_user_id: int) -> dict:
    """Automatically searches for a movie, finds the first file, triggers the download, and forwards it."""
    if not userbot_client:
        return {"error": "Userbot not running"}

    file_received = asyncio.Event()
    result = {"status": "timeout", "message": "Failed to get file within the time limit."}

    from telethon.tl.types import MessageMediaDocument

    async def media_handler(event):
        try:
            if event.message.media and isinstance(event.message.media, MessageMediaDocument):
                logger.info(f"Caught file from {bot_username}, forwarding to {target_user_id}")
                
                # Prepend the bot name to the message text so the user knows which bot it came from
                original_text = event.message.text or ""
                new_text = f"🤖 **Source:** {bot_username}\n\n{original_text}"
                
                await userbot_client.send_message(
                    target_user_id, 
                    file=event.message.media, 
                    message=new_text
                )
                result["status"] = "success"
                result["message"] = f"File successfully forwarded to {target_user_id}"
                file_received.set()
        except Exception as e:
            result["status"] = "error"
            result["message"] = f"Failed to forward: {str(e)}"
            file_received.set()

    userbot_client.add_event_handler(media_handler, events.NewMessage(chats=bot_username))

    try:
        logger.info(f"Auto-forward: Sending query '{query}' to {bot_username}")
        await userbot_client.send_message(bot_username, query)
        
        triggered = False
        
        # We poll for up to 30 iterations to handle multi-stage menus
        for _ in range(30):
            if triggered: break
            await asyncio.sleep(1.5)
            msgs = await userbot_client.get_messages(bot_username, limit=3)
            
            for msg in msgs:
                if triggered: break
                
                # 1. Check for EzPz style embedded deep links
                if msg.entities:
                    for entity in msg.entities:
                        if hasattr(entity, 'url') and "?start=" in entity.url:
                            start_param = entity.url.split("?start=")[1]
                            command = f"/start {start_param}"
                            logger.info(f"Auto-forward: Found EzPz link, sending command {command}")
                            await userbot_client.send_message(bot_username, command)
                            triggered = True
                            break
                            
                # 2. Check for Inline Buttons (A2bot and DeltaBot)
                if not triggered and msg.reply_markup and hasattr(msg.reply_markup, 'rows'):
                    for row in msg.reply_markup.rows:
                        if triggered: break
                        for button in row.buttons:
                            if hasattr(button, 'data'):
                                # If it's a file button that triggers a deep link (like A2Bot)
                                if button.data.startswith(b'file#') or button.data.startswith(b'send#'):
                                    logger.info("Auto-forward: Found final file button, clicking it...")
                                    cb_result = await msg.click(data=button.data)
                                    if hasattr(cb_result, 'url') and cb_result.url and "?start=" in cb_result.url:
                                        start_param = cb_result.url.split("?start=")[1]
                                        command = f"/start {start_param}"
                                        logger.info(f"Auto-forward: Extracted deep link, sending {command}")
                                        await userbot_client.send_message(bot_username, command)
                                    # Even if there's no URL, it might just send the file directly
                                    triggered = True
                                    break
                                
                                # If it's a nested menu folder (DeltaBot), click it and wait for the message to update
                                elif button.data.startswith(b'fold#') or button.data.startswith(b'open_grp'):
                                    # Only click the FIRST folder we see to drill down
                                    safe_text = button.text.encode('ascii','ignore').decode() if hasattr(button, 'text') else 'Folder'
                                    logger.info(f"Auto-forward: Found nested menu '{safe_text}', drilling down...")
                                    await msg.click(data=button.data)
                                    # Break out to re-fetch the updated messages!
                                    break
                        
                        # If we clicked a folder, break row loop
                        if not triggered and any(hasattr(b, 'data') and (b.data.startswith(b'fold#') or b.data.startswith(b'open_grp')) for b in row.buttons):
                            break
                    
        if not triggered:
            error_msg = f"❌ **Not Found:** Could not find any results for `{query}` on {bot_username}."
            logger.info(f"Auto-forward: {error_msg}")
            await userbot_client.send_message(target_user_id, error_msg)
            # Return success because we successfully handled the failure by notifying the user
            return {"status": "success", "message": "Could not find movie, but successfully sent 'Not Found' message to user."}
            
        # Wait up to 25 seconds for the actual file to arrive
        try:
            await asyncio.wait_for(file_received.wait(), timeout=25.0)
        except asyncio.TimeoutError:
            if not file_received.is_set():
                error_msg = f"⚠️ **Timeout:** {bot_username} took too long to send the file for `{query}`."
                logger.error(f"Auto-forward: {error_msg}")
                await userbot_client.send_message(target_user_id, error_msg)
                # Return success because we successfully notified the user of the timeout
                result["status"] = "success"
                result["message"] = "Timeout waiting for file, but successfully sent 'Timeout' message to user."
            
    finally:
        userbot_client.remove_event_handler(media_handler, events.NewMessage(chats=bot_username))
        
    return result
