# Universal Movie Bot Relay API

A powerful backend microservice built with **FastAPI** and **Telethon**. This tool acts as an invisible bridge between your frontend bot and third-party Telegram movie bots. It scrapes multi-layered bot menus, automatically interacts with buttons and deep links, and silently forwards physical movie files to your users.

## Features
- 🚀 **FastAPI Integration:** Fully accessible via simple HTTP GET requests.
- 🤖 **Universal Bot Support:** Intelligently handles standard bots, Deep Link bots (EzPzBot), and Multi-Folder Recursive bots (DeltaBot).
- ⚡ **Auto-Forwarding:** Bypasses manual clicking by silently doing all the work in the background and dropping the file into the user's DMs.
- 🚦 **Robust Error Handling:** Telegram users get native messages if a movie is not found or a bot times out.

---

## 🛠️ Environment Variables

To run this backend, you must configure the following in your `.env` file (or Render dashboard):

| Key | Description | Example |
| :--- | :--- | :--- |
| `API_ID` | Your Telegram API ID | `1234567` |
| `API_HASH` | Your Telegram API Hash | `a1b2c3d4e5...` |
| `TARGET_USER_ID` | The Telegram ID where files are forwarded | `8338474200` |
| `SESSION_NAME` | The string session file name | `relay_userbot` |
| `THIRD_PARTY_BOT_USERNAMES` | Comma-separated list of bots to search | `@ipapkornEzPzBot,@ipapkornA2bot,@iPapkornDeltaBot` |

*(Note: When deploying to Render, you should also add `PYTHON_VERSION=3.11.0`)*

---

## 📡 API Documentation

### 1. `GET /search`
Silently searches all target bots and returns a clean JSON list of available movies. Does **not** download files.
* **Parameters:** `query` (str)
* **Example:** `/search?query=Jailer 2023`

### 2. `GET /auto_download`
Navigates the menu of **one specific bot** and forwards the requested file to the `TARGET_USER_ID`.
* **Parameters:** 
  * `query` (str) — The movie name
  * `bot` (str) — The exact username of the target bot
* **Example:** `/auto_download?query=Jailer 2023&bot=@iPapkornDeltaBot`

### 3. `GET /auto_download_all`
Hits **all configured bots simultaneously** and forwards every matching file it can find.
* **Parameters:** `query` (str)
* **Example:** `/auto_download_all?query=Jailer 2023`

---

## 🚀 Deployment (Render.com)

1. Ensure `*.session` is **removed** from your `.gitignore` file.
2. Push your code (and the `relay_userbot.session` file) to a **Private** GitHub repository.
3. Create a **Web Service** on Render linked to your repo.
4. Set the Build Command: `pip install -r requirements.txt`
5. Set the Start Command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
6. Enter all the Environment Variables above.
7. Click Deploy!
