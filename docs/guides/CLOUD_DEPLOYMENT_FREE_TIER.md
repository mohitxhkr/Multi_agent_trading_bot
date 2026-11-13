# ☁️ 24/7 Cloud Deployment Guide (100% Free Tier)

Deploy your Delta Exchange Multi-Agent Trading Bot to the cloud so it runs **24 hours a day, 7 days a week**, completely independent of your local PC.

---

## 🏆 Option 1: Render.com (Recommended — 3 Minutes, No Credit Card Required)

Render provides **750 free hours every month** (enough for the whole month 24/7).

### Step 1: Push Project to GitHub
1. Create a free account at [github.com](https://github.com) if you haven't already.
2. Create a new **Private Repository** (e.g. `delta-trading-bot`).
3. Push this project folder to your private repo:
   ```bash
   git init
   git add .
   git commit -m "Deploy Delta Multi-Agent Bot"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USERNAME>/delta-trading-bot.git
   git push -u origin main
   ```

### Step 2: Deploy on Render
1. Go to [render.com](https://render.com) and sign up with your GitHub account.
2. Click **New +** $\rightarrow$ **Web Service**.
3. Select your `delta-trading-bot` repository.
4. Fill in the basic settings:
   * **Name:** `delta-trading-bot`
   * **Runtime:** `Python 3`
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `python server.py`
   * **Instance Type:** `Free`
5. Click **Advanced** $\rightarrow$ **Add Environment Variable** and paste your secrets:
   * `DELTA_API_KEY`: *(Your Delta Exchange API key)*
   * `DELTA_API_SECRET`: *(Your Delta Exchange API secret)*
   * `TELEGRAM_BOT_TOKEN`: *(Your Telegram Bot token from @BotFather)*
   * `TELEGRAM_CHAT_ID`: *(Your Telegram numeric Chat ID)*
   * `BTC_LEVERAGE`: `50`
   * `ALT_LEVERAGE`: `25`
   * `CAPITAL_ALLOCATION_MIN_PCT`: `0.75`
6. Click **Create Web Service**. Your bot will build and start scanning within 60 seconds!

### Step 3: Keep It Awake 24/7 (Prevent Free Tier Sleep)
Render free web services sleep after 15 minutes of no web traffic. You can prevent this completely for free:
1. Copy your Render service URL (e.g., `https://delta-trading-bot.onrender.com`).
2. Go to [uptimerobot.com](https://uptimerobot.com) (100% free account).
3. Click **Add New Monitor**:
   * **Monitor Type:** `HTTP(s)`
   * **Friendly Name:** `Delta Bot Health`
   * **URL:** `https://delta-trading-bot.onrender.com/health`
   * **Monitoring Interval:** `Every 5 minutes`
4. Click **Create Monitor**. 
*UptimeRobot will ping the `/health` endpoint every 5 minutes, ensuring your bot stays awake 24/7/365 without ever shutting down!*

---

## 🛡️ Option 2: Oracle Cloud Free Tier (Always Free Linux VPS)

If you prefer a dedicated Linux server where you have full SSH terminal control:

1. Sign up for **Oracle Cloud Always Free Tier** at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/).
2. Create an **Ubuntu 24.04 Compute Instance** (free forever, 1 GB RAM or 24 GB ARM).
3. Connect via SSH:
   ```bash
   ssh ubuntu@<YOUR_SERVER_IP>
   ```
4. Clone your repo and install dependencies:
   ```bash
   sudo apt update && sudo apt install -y python3-pip git
   git clone <YOUR_REPO_URL>
   cd "Multi Agent Trading Bot"
   pip install -r requirements.txt
   ```
5. Run the bot permanently in the background using `systemd` or `nohup`:
   ```bash
   nohup python3 run_247_scanner.py --interval 120 > scanner.log 2>&1 &
   ```
*The process will run continuously 24/7 on Oracle's cloud servers forever without stopping.*

---

## 📊 Live Verification

Once deployed to Render or a cloud host, visit:
```
https://<YOUR_APP_URL>/health
```
You will see real-time JSON status:
```json
{
  "bot": "Delta Exchange Multi-Agent 24/7 Trading Bot",
  "status": "ACTIVE_SCANNING",
  "cycles_completed": 142,
  "last_scan": "2026-10-30 19:25:00 UTC",
  "uptime_started": "2026-10-30 14:10:00 UTC"
}
```
And whenever a liquidity sweep trade triggers, you'll receive your instant alert on Telegram!

