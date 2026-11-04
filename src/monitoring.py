"""
Monitoring & Observability System for Multi-Agent Trading Architecture.
Tracks agent execution latency, API error rates, trade rejection reasons,
exchange connectivity health, and Telegram alert delivery.
"""

import time
import json
import os
import logging
from typing import Dict, Any, List, Optional
from collections import defaultdict

logger = logging.getLogger("monitoring")


class SystemMonitor:
    """Central observability metrics collector and health reporter."""

    def __init__(self, metrics_file: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        state_dir = os.path.join(base_dir, "state")
        os.makedirs(state_dir, exist_ok=True)
        self.metrics_file = metrics_file or os.path.join(state_dir, "system_metrics.json")
        self.start_time = time.time()
        
        # Operational counters
        self.agent_latencies = defaultdict(list)
        self.api_call_counts = defaultdict(int)
        self.api_error_counts = defaultdict(int)
        self.api_latencies = defaultdict(list)
        self.rejection_reasons = defaultdict(int)
        self.cycles_completed = 0
        self.telegram_deliveries = {"success": 0, "failure": 0}
        self.recent_events: List[Dict[str, Any]] = []

    def record_agent_duration(self, agent_name: str, duration_ms: float, status: str = "SUCCESS"):
        """Record the execution duration of an agent."""
        self.agent_latencies[agent_name].append(duration_ms)
        # Keep recent 100 entries
        if len(self.agent_latencies[agent_name]) > 100:
            self.agent_latencies[agent_name].pop(0)

        self._add_event("AGENT_EXECUTION", {
            "agent": agent_name,
            "duration_ms": round(duration_ms, 2),
            "status": status
        })

    def record_api_call(self, endpoint: str, latency_ms: float, success: bool = True, error: Optional[str] = None):
        """Track Delta Exchange API performance."""
        self.api_call_counts[endpoint] += 1
        if not success:
            self.api_error_counts[endpoint] += 1
        self.api_latencies[endpoint].append(latency_ms)
        if len(self.api_latencies[endpoint]) > 100:
            self.api_latencies[endpoint].pop(0)

        if not success:
            self._add_event("API_ERROR", {
                "endpoint": endpoint,
                "latency_ms": round(latency_ms, 2),
                "error": error
            })

    def record_trade_rejection(self, code: str, symbol: str, reason: str):
        """Categorize and count candidate rejections."""
        self.rejection_reasons[code] += 1
        self._add_event("TRADE_REJECTION", {
            "code": code,
            "symbol": symbol,
            "reason": reason
        })

    def record_telegram_delivery(self, success: bool, message_type: str = "alert"):
        """Track Telegram notification delivery reliability."""
        if success:
            self.telegram_deliveries["success"] += 1
        else:
            self.telegram_deliveries["failure"] += 1
            self._add_event("TELEGRAM_FAILURE", {"type": message_type})

    def increment_cycle(self):
        """Track completed trading scans."""
        self.cycles_completed += 1

    def _add_event(self, event_type: str, details: Dict[str, Any]):
        event = {
            "timestamp": time.time(),
            "type": event_type,
            "details": details
        }
        self.recent_events.append(event)
        if len(self.recent_events) > 200:
            self.recent_events.pop(0)

    def get_health_report(self) -> Dict[str, Any]:
        """Generate high-level operational health report."""
        uptime_seconds = time.time() - self.start_time
        
        # Calculate average agent durations
        avg_agent_durations = {}
        for agent, times in self.agent_latencies.items():
            if times:
                avg_agent_durations[agent] = round(sum(times) / len(times), 2)

        # Calculate API error rate
        total_api = sum(self.api_call_counts.values())
        total_err = sum(self.api_error_counts.values())
        api_error_rate_pct = round((total_err / total_api * 100), 2) if total_api > 0 else 0.0

        telegram_total = self.telegram_deliveries["success"] + self.telegram_deliveries["failure"]
        tg_success_rate = round((self.telegram_deliveries["success"] / telegram_total * 100), 1) if telegram_total > 0 else 100.0

        report = {
            "status": "HEALTHY" if api_error_rate_pct < 5.0 and tg_success_rate > 90.0 else "DEGRADED",
            "uptime_seconds": round(uptime_seconds, 1),
            "cycles_completed": self.cycles_completed,
            "api_metrics": {
                "total_calls": total_api,
                "total_errors": total_err,
                "error_rate_pct": api_error_rate_pct,
                "calls_by_endpoint": dict(self.api_call_counts)
            },
            "telegram_metrics": {
                "success": self.telegram_deliveries["success"],
                "failure": self.telegram_deliveries["failure"],
                "success_rate_pct": tg_success_rate
            },
            "agent_performance_ms": avg_agent_durations,
            "top_rejection_reasons": dict(sorted(self.rejection_reasons.items(), key=lambda x: x[1], reverse=True)[:5]),
            "recent_events_count": len(self.recent_events)
        }
        return report

    def save_metrics(self):
        """Dump current metrics to disk for persistent observability."""
        try:
            report = self.get_health_report()
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save system metrics: {e}")

