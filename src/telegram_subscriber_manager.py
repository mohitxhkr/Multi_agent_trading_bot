"""
Telegram Subscriber Manager for Delta AI Market Intelligence.
Maintains persistent subscriptions for automated broadcasts:
  1. Daily Morning Crypto News Briefing (10:00 AM IST)
  2. Important Pre-Trade Key Levels & Breakout/Breakdown Radar Alerts
  3. Live Candlestick Charts

Distinguishes between Administrator (live trading permitted) and Guests (market intelligence only).
"""

import os
import json
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("telegram-subscribers")

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
SUBSCRIBERS_FILE = os.path.join(STATE_DIR, "telegram_subscribers.json")


def _get_current_ist_str() -> str:
    ist_zone = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist_zone).strftime("%Y-%m-%d %H:%M:%S IST")


class TelegramSubscriberManager:
    """Manages Telegram broadcast subscribers with thread-safe file operations."""

    def __init__(self, subscribers_file: Optional[str] = None):
        self.file_path = subscribers_file or SUBSCRIBERS_FILE
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Ensure state file and directory exist."""
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            try:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump({}, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to initialize subscribers file: {e}")

    def load_subscribers(self) -> Dict[str, Dict[str, Any]]:
        """Load all subscriber records from disk."""
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        except Exception as e:
            logger.error(f"Error loading subscribers from {self.file_path}: {e}")
        return {}

    def save_subscribers(self, subs: Dict[str, Dict[str, Any]]) -> bool:
        """Atomically persist subscribers to disk."""
        tmp_path = f"{self.file_path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(subs, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.file_path)
            return True
        except Exception as e:
            logger.error(f"Error saving subscribers to {self.file_path}: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False

    def register_subscriber(
        self,
        chat_id: Any,
        user_info: Optional[Dict[str, Any]] = None,
        role: str = "guest",
        active: bool = True
    ) -> bool:
        """
        Auto-register or update a subscriber when they message the bot.
        """
        cid = str(chat_id).strip()
        if not cid:
            return False

        uinfo = user_info or {}
        username = uinfo.get("username") or ""
        first_name = uinfo.get("first_name") or ""
        last_name = uinfo.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip() or "Guest"

        subs = self.load_subscribers()
        existing = subs.get(cid, {})

        now_str = _get_current_ist_str()
        subs[cid] = {
            "chat_id": cid,
            "username": username or existing.get("username", ""),
            "name": full_name or existing.get("name", "Guest"),
            "role": role if role in ["admin", "guest"] else existing.get("role", "guest"),
            "active": active if active is not None else existing.get("active", True),
            "news_enabled": existing.get("news_enabled", True),
            "levels_enabled": existing.get("levels_enabled", True),
            "registered_at": existing.get("registered_at", now_str),
            "last_seen_at": now_str
        }

        return self.save_subscribers(subs)

    def unregister_subscriber(self, chat_id: Any) -> bool:
        """Mark a subscriber as inactive (unsubscribed)."""
        cid = str(chat_id).strip()
        subs = self.load_subscribers()
        if cid in subs:
            subs[cid]["active"] = False
            subs[cid]["unsubscribed_at"] = _get_current_ist_str()
            return self.save_subscribers(subs)
        return False

    def get_active_subscribers(self, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Return list of active subscribers.
        topic: 'news', 'levels', or None (any active).
        """
        subs = self.load_subscribers()
        results = []
        for s in subs.values():
            if not s.get("active", True):
                continue
            if topic == "news" and not s.get("news_enabled", True):
                continue
            if topic == "levels" and not s.get("levels_enabled", True):
                continue
            results.append(s)
        return results

    def mark_subscriber_blocked(self, chat_id: Any) -> bool:
        """Mark subscriber inactive if they blocked the bot or chat is dead."""
        cid = str(chat_id).strip()
        subs = self.load_subscribers()
        if cid in subs:
            subs[cid]["active"] = False
            subs[cid]["error"] = "BOT_BLOCKED_OR_CHAT_UNREACHABLE"
            subs[cid]["deactivated_at"] = _get_current_ist_str()
            return self.save_subscribers(subs)
        return False

    def count_summary(self) -> Dict[str, int]:
        """Return subscriber count breakdown."""
        subs = self.load_subscribers()
        active_guests = 0
        active_admins = 0
        inactive = 0
        for s in subs.values():
            if s.get("active", True):
                if s.get("role") == "admin":
                    active_admins += 1
                else:
                    active_guests += 1
            else:
                inactive += 1
        return {
            "total_registered": len(subs),
            "active_total": active_guests + active_admins,
            "active_guests": active_guests,
            "active_admins": active_admins,
            "inactive": inactive
        }
