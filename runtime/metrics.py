"""Prometheus-style metrics collection for RetailOS.

Tracks:
- Request count and latency per endpoint
- Error rates
- Active connections
- Business metrics (orders, revenue)
- System uptime

Exposes metrics in Prometheus text format and JSON.
"""

import time
from collections import defaultdict
from typing import Any


class MetricsCollector:
    """In-memory metrics collection with Prometheus-compatible output."""

    def __init__(self):
        self._start_time = time.time()
        self._request_count: dict[str, int] = defaultdict(int)
        self._request_errors: dict[str, int] = defaultdict(int)
        self._request_latency_sum: dict[str, float] = defaultdict(float)
        self._request_latency_count: dict[str, int] = defaultdict(int)
        self._request_latency_max: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._counters: dict[str, int] = defaultdict(int)
        self._active_requests = 0

    # ── Request Metrics ──

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float):
        """Record a completed HTTP request."""
        key = f"{method} {path}"
        self._request_count[key] += 1
        self._request_latency_sum[key] += duration_ms
        self._request_latency_count[key] += 1
        self._request_latency_max[key] = max(self._request_latency_max[key], duration_ms)

        if status_code >= 400:
            self._request_errors[key] += 1

        # Status code counters
        self._counters[f"http_{status_code // 100}xx"] += 1

    def request_started(self):
        self._active_requests += 1

    def request_finished(self):
        self._active_requests = max(0, self._active_requests - 1)

    # ── Custom Metrics ──

    def increment(self, name: str, value: int = 1):
        """Increment a counter metric."""
        self._counters[name] += value

    def set_gauge(self, name: str, value: float):
        """Set a gauge metric."""
        self._gauges[name] = value

    # ── Getters ──

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def get_summary(self) -> dict[str, Any]:
        """Get full metrics summary as JSON."""
        total_requests = sum(self._request_count.values())
        total_errors = sum(self._request_errors.values())

        # Top endpoints by request count
        top_endpoints = sorted(
            self._request_count.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:15]

        # Slowest endpoints
        slowest = []
        for key, count in self._request_latency_count.items():
            avg = self._request_latency_sum[key] / count if count else 0
            slowest.append({
                "endpoint": key,
                "avg_ms": round(avg, 1),
                "max_ms": round(self._request_latency_max[key], 1),
                "count": count,
            })
        slowest.sort(key=lambda x: x["avg_ms"], reverse=True)

        return {
            "uptime_seconds": round(self.uptime_seconds, 0),
            "uptime_human": self._format_uptime(),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": round(total_errors / max(total_requests, 1) * 100, 2),
            "active_requests": self._active_requests,
            "requests_per_minute": round(total_requests / max(self.uptime_seconds / 60, 1), 1),
            "status_codes": {
                "2xx": self._counters.get("http_2xx", 0),
                "3xx": self._counters.get("http_3xx", 0),
                "4xx": self._counters.get("http_4xx", 0),
                "5xx": self._counters.get("http_5xx", 0),
            },
            "top_endpoints": [
                {"endpoint": ep, "count": count}
                for ep, count in top_endpoints
            ],
            "slowest_endpoints": slowest[:10],
            "gauges": dict(self._gauges),
            "counters": dict(self._counters),
        }

    def get_prometheus_text(self) -> str:
        """Export metrics in Prometheus text exposition format."""
        lines = []

        # Uptime
        lines.append("# HELP retailos_uptime_seconds Server uptime in seconds")
        lines.append("# TYPE retailos_uptime_seconds gauge")
        lines.append(f"retailos_uptime_seconds {self.uptime_seconds:.0f}")

        # Request count
        lines.append("# HELP retailos_http_requests_total Total HTTP requests")
        lines.append("# TYPE retailos_http_requests_total counter")
        for key, count in self._request_count.items():
            method, path = key.split(" ", 1)
            lines.append(f'retailos_http_requests_total{{method="{method}",path="{path}"}} {count}')

        # Error count
        lines.append("# HELP retailos_http_errors_total Total HTTP errors")
        lines.append("# TYPE retailos_http_errors_total counter")
        for key, count in self._request_errors.items():
            method, path = key.split(" ", 1)
            lines.append(f'retailos_http_errors_total{{method="{method}",path="{path}"}} {count}')

        # Latency
        lines.append("# HELP retailos_http_request_duration_ms Request duration in ms")
        lines.append("# TYPE retailos_http_request_duration_ms summary")
        for key, count in self._request_latency_count.items():
            avg = self._request_latency_sum[key] / count if count else 0
            method, path = key.split(" ", 1)
            lines.append(f'retailos_http_request_duration_ms{{method="{method}",path="{path}",quantile="avg"}} {avg:.1f}')
            lines.append(f'retailos_http_request_duration_ms{{method="{method}",path="{path}",quantile="max"}} {self._request_latency_max[key]:.1f}')

        # Active requests
        lines.append("# HELP retailos_active_requests Current active requests")
        lines.append("# TYPE retailos_active_requests gauge")
        lines.append(f"retailos_active_requests {self._active_requests}")

        # Custom gauges
        for name, value in self._gauges.items():
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f"retailos_{safe_name} {value}")

        return "\n".join(lines) + "\n"

    def _format_uptime(self) -> str:
        seconds = int(self.uptime_seconds)
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {seconds % 60}s"


# Singleton
metrics = MetricsCollector()
