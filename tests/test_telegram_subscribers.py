import os
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.telegram_subscriber_manager import TelegramSubscriberManager
from src.telegram_notifier import TelegramNotifier


class TestTelegramSubscriberManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sub_file = os.path.join(self.temp_dir.name, "subscribers.json")
        self.mgr = TelegramSubscriberManager(subscribers_file=self.sub_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_register_and_load_subscribers(self):
        # Register an admin and a guest
        self.mgr.register_subscriber("123456789", {"username": "admin_user", "first_name": "Admin"}, role="admin")
        self.mgr.register_subscriber("11223344", {"username": "guest_trader", "first_name": "Guest"}, role="guest")

        subs = self.mgr.load_subscribers()
        self.assertIn("123456789", subs)
        self.assertIn("11223344", subs)
        self.assertEqual(subs["123456789"]["role"], "admin")
        self.assertEqual(subs["11223344"]["role"], "guest")

        active = self.mgr.get_active_subscribers()
        self.assertEqual(len(active), 2)

    def test_unregister_and_re_subscribe(self):
        self.mgr.register_subscriber("11223344", {"first_name": "Guest"}, role="guest")
        self.assertTrue(self.mgr.unregister_subscriber("11223344"))

        subs = self.mgr.load_subscribers()
        self.assertFalse(subs["11223344"]["active"])

        active = self.mgr.get_active_subscribers()
        self.assertEqual(len(active), 0)

        # Re-subscribe
        self.mgr.register_subscriber("11223344", active=True)
        active = self.mgr.get_active_subscribers()
        self.assertEqual(len(active), 1)

    def test_subscriber_count_summary(self):
        self.mgr.register_subscriber("1", role="admin")
        self.mgr.register_subscriber("2", role="guest")
        self.mgr.register_subscriber("3", role="guest")
        self.mgr.unregister_subscriber("3")

        summary = self.mgr.count_summary()
        self.assertEqual(summary["total_registered"], 3)
        self.assertEqual(summary["active_total"], 2)
        self.assertEqual(summary["active_admins"], 1)
        self.assertEqual(summary["active_guests"], 1)
        self.assertEqual(summary["inactive"], 1)

    def test_broadcast_message_delivery(self):
        notifier = TelegramNotifier(bot_token="test_token", chat_id="123456789", enabled=True)
        notifier.subscriber_manager = self.mgr
        self.mgr.register_subscriber("123456789", role="admin")
        self.mgr.register_subscriber("77777777", role="guest")

        with patch("requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"ok": True, "result": {"message_id": 123}}
            delivered = notifier.broadcast_message("<b>Pre-Trade Breakout Radar</b>")
            self.assertEqual(delivered, 2)
            # Should have posted to both 123456789 and 77777777
            called_chats = [call[1]["json"]["chat_id"] for call in mock_post.call_args_list]
            self.assertIn("123456789", called_chats)
            self.assertIn("77777777", called_chats)


if __name__ == "__main__":
    unittest.main()
