"""Unit tests for cloud healthcheck endpoints in server.py (UptimeRobot & Render safety)."""

import io
import json
import unittest
from unittest.mock import MagicMock, patch

import server


def _invoke_handler(method: str, path: str):
    """Instantiate HealthCheckHandler without binding a real socket."""
    handler = server.HealthCheckHandler.__new__(server.HealthCheckHandler)
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.command = method
    handler.client_address = ("127.0.0.1", 12345)
    handler.headers = {}
    handler.rfile = io.BytesIO()
    raw_out = io.BytesIO()
    handler.wfile = raw_out

    status_holder = {"code": None, "headers": {}}

    def _send_response(code, message=None):
        status_holder["code"] = code

    def _send_header(keyword, value):
        status_holder["headers"][keyword] = value

    def _end_headers():
        pass

    handler.send_response = _send_response
    handler.send_header = _send_header
    handler.end_headers = _end_headers

    if method == "HEAD":
        handler.do_HEAD()
    elif method == "GET":
        handler.do_GET()
    else:
        raise ValueError(f"Unsupported method {method}")

    body_text = raw_out.getvalue().decode("utf-8")
    parsed_json = json.loads(body_text) if body_text else None
    return status_holder["code"], status_holder["headers"], parsed_json


class TestServerHealth(unittest.TestCase):
    def test_server_class_is_threaded_and_reusable(self):
        self.assertTrue(issubclass(server.ReusableThreadingHTTPServer, server.ThreadingHTTPServer))
        self.assertTrue(server.ReusableThreadingHTTPServer.allow_reuse_address)
        self.assertTrue(server.ReusableThreadingHTTPServer.daemon_threads)

    def test_head_health_paths_and_query_params(self):
        for path in ["/", "/health", "/health/", "/health?t=1731312000", "/status", "/ping", "/healthz"]:
            code, headers, body = _invoke_handler("HEAD", path)
            self.assertEqual(code, 200, f"HEAD {path} should return 200")
            self.assertEqual(headers.get("Content-Type"), "application/json")
            self.assertIsNone(body)

    def test_head_unknown_returns_404(self):
        code, _, _ = _invoke_handler("HEAD", "/does-not-exist")
        self.assertEqual(code, 404)

    @patch("server.DeltaExchangeClient")
    def test_get_health_does_not_block_on_external_exchange_api(self, mock_client_cls):
        for path in ["/", "/health", "/health/", "/health?cachebust=123", "/status", "/ping"]:
            code, headers, payload = _invoke_handler("GET", path)
            self.assertEqual(code, 200, f"GET {path} should return 200")
            self.assertEqual(headers.get("Content-Type"), "application/json")
            self.assertIn("Cache-Control", headers)
            self.assertEqual(payload["diagnostics_mode"], "cached")
            self.assertIn("status", payload)
            self.assertIn("cycles_completed", payload)

        mock_client_cls.assert_not_called()

    @patch("server.DeltaExchangeClient")
    def test_get_health_live_flag_queries_exchange_diagnostics(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.test_connection.return_value = {"authenticated": True, "message": "OK"}
        mock_client.get_positions.return_value = {
            "success": True,
            "result": [{"symbol": "BTCUSD", "size": 2}, {"symbol": "ETHUSD", "size": 0}],
        }
        mock_client_cls.return_value = mock_client

        code, _, payload = _invoke_handler("GET", "/health?live=1")
        self.assertEqual(code, 200)
        self.assertEqual(payload["diagnostics_mode"], "live")
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["active_positions_count"], 1)
        self.assertEqual(payload["active_symbols"], ["BTCUSD"])

    def test_trigger_routes_handle_query_strings(self):
        mock_orch = MagicMock()
        mock_orch.check_and_dispatch_daily_morning_briefing.return_value = True
        mock_orch.check_and_dispatch_daily_market_levels.return_value = True

        with patch.object(server, "_active_orchestrator", mock_orch):
            code_news, _, body_news = _invoke_handler("GET", "/trigger-morning-news?t=1")
            code_levels, _, body_levels = _invoke_handler("GET", "/trigger-levels/")

        self.assertEqual(code_news, 200)
        self.assertEqual(body_news, {"triggered": True, "dispatched": True})
        mock_orch.check_and_dispatch_daily_morning_briefing.assert_called_once_with(force=True)

        self.assertEqual(code_levels, 200)
        self.assertEqual(body_levels, {"triggered": True, "dispatched": True})
        mock_orch.check_and_dispatch_daily_market_levels.assert_called_once_with(force=True)

    def test_get_unknown_returns_404_json(self):
        code, _, payload = _invoke_handler("GET", "/unknown/path?x=1")
        self.assertEqual(code, 404)
        self.assertEqual(payload, {"error": "Not found", "path": "/unknown/path"})


if __name__ == "__main__":
    unittest.main()
