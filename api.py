from fastapi import FastAPI, HTTPException
import asyncio
from pydantic import BaseModel
from relay import start_relay, stop_relay, get_movie_info, auto_forward_movie
import uvicorn
import os

app = FastAPI(title="Movie Bot Relay API", version="1.0")

class MovieResult(BaseModel):
    bot: str
    movie_name: str
    key: str | None = None

class SearchResponse(BaseModel):
    status: str
    query: str
    results: list[MovieResult]

class AutoDownloadResponse(BaseModel):
    status: str
    message: str

@app.on_event("startup")
async def startup_event():
    # Start the telethon userbot bridge in the background
    await start_relay()

@app.on_event("shutdown")
async def shutdown_event():
    # Cleanly disconnect
    await stop_relay()

@app.get("/search", response_model=SearchResponse)
async def search_movie(query: str):
    """
    Search for a movie via the Telegram userbot bridge.
    Returns a structured list of bot usernames, movie names, and optional deep link keys.
    """
    if not query or len(query) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters.")
        
    try:
        responses = await get_movie_info(query)
        final_results = []
        
        # Responses is now a list of dictionaries (one from each bot)
        for response in responses:
            if isinstance(response, dict) and "error" not in response:
                bot_name = response.get("sender", "UnknownBot")
                links = response.get("embedded_links", [])
                buttons = response.get("buttons", [])
                
                # 1. Parse Embedded Links (e.g., EzPzBot)
                for link in links:
                    url = link.get("url", "")
                    title = link.get("text", "Movie")
                    if "?start=" in url:
                        key = url.split("?start=")[-1]
                        final_results.append(MovieResult(bot=bot_name, movie_name=title, key=f"/start {key}"))
                    else:
                        final_results.append(MovieResult(bot=bot_name, movie_name=title))
                
                # 2. Parse Buttons (e.g., A2bot)
                if not links and buttons:
                    for btn in buttons:
                        title = btn.get("text", "")
                        # Filter out purely navigational buttons like "▫️ Pages" or "1/1"
                        if len(title) > 5 and "Pages" not in title and "/" not in title:
                            final_results.append(MovieResult(bot=bot_name, movie_name=title))
        
        return SearchResponse(status="success", query=query, results=final_results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auto_download", response_model=AutoDownloadResponse)
async def auto_download(query: str, bot: str):
    """
    Fully automate the flow: Search -> Click -> Extract -> Forward.
    Forwards the physical file to TARGET_USER_ID.
    """
    if not query or len(query) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters.")
    if not bot.startswith("@"):
        bot = f"@{bot}"
        
    target_user_id = int(os.getenv("TARGET_USER_ID", "8338474200"))
    
    try:
        result = await auto_forward_movie(query, bot, target_user_id)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))
        return AutoDownloadResponse(status=result.get("status"), message=result.get("message"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auto_download_all", response_model=AutoDownloadResponse)
async def auto_download_all(query: str):
    """
    Simultaneously scrape and download the movie from ALL target bots at once.
    """
    from relay import target_bots
    
    if not query or len(query) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters.")
        
    target_user_id = int(os.getenv("TARGET_USER_ID", "8338474200"))
    
    try:
        # Run auto_forward_movie concurrently for all bots
        tasks = [auto_forward_movie(query, bot, target_user_id) for bot in target_bots]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = 0
        for r in results:
            if isinstance(r, dict) and r.get("status") == "success":
                success_count += 1
                
        if success_count > 0:
            return AutoDownloadResponse(status="success", message=f"Successfully forwarded files from {success_count}/{len(target_bots)} bots to {target_user_id}")
        else:
            return AutoDownloadResponse(status="error", message="Failed to find or forward the movie from any bot.")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
