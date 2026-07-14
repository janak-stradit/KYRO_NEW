"""
monitoring/monitor.py — Pipeline monitoring, alerting, and performance metrics.
Tracks: memory, CPU, execution duration, quality scores, row counts.
Alerts when quality drops below threshold.
"""
from __future__ import annotations

import logging
import os
import platform
import time
from datetime import datetime, timezone
from typing import Any

import psutil

logger = logging.getLogger(__name__)


class PipelineMonitor:
    """
    Lightweight system resource monitor for pipeline execution.
    Samples CPU/memory at start and end; logs peak values.

    Usage::
        monitor = PipelineMonitor()
        monitor.start()
        # ... run pipeline ...
        metrics = monitor.stop()
    """

    def __init__(self) -> None:
        self._proc = psutil.Process(os.getpid())
        self._start_time: float = 0.0
        self._peak_memory_mb: float = 0.0
        self._cpu_samples: list[float] = []
        self._running = False

    def start(self) -> None:
        self._start_time = time.perf_counter()
        self._running = True
        self._peak_memory_mb = self._current_memory_mb()
        logger.info(
            "Monitor started | host=%s | pid=%d | mem_start=%.1f MB",
            platform.node(), os.getpid(), self._peak_memory_mb,
        )

    def sample(self) -> dict:
        """Take a sample — call periodically during execution."""
        if not self._running:
            return {}
        mem = self._current_memory_mb()
        cpu = self._proc.cpu_percent(interval=0.1)
        self._peak_memory_mb = max(self._peak_memory_mb, mem)
        self._cpu_samples.append(cpu)
        return {"memory_mb": round(mem, 1), "cpu_percent": round(cpu, 1)}

    def stop(self) -> dict:
        """Stop monitoring and return collected metrics."""
        self._running = False
        elapsed = time.perf_counter() - self._start_time
        avg_cpu = sum(self._cpu_samples) / max(len(self._cpu_samples), 1)
        metrics = {
            "duration_seconds": round(elapsed, 3),
            "peak_memory_mb": round(self._peak_memory_mb, 1),
            "avg_cpu_percent": round(avg_cpu, 1),
            "host": platform.node(),
            "pid": os.getpid(),
            "python_version": platform.python_version(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(
            "Monitor stopped | duration=%.2fs | peak_mem=%.1f MB | avg_cpu=%.1f%%",
            elapsed, self._peak_memory_mb, avg_cpu,
        )
        return metrics

    def _current_memory_mb(self) -> float:
        return self._proc.memory_info().rss / (1024 ** 2)


class QualityAlertManager:
    """
    Sends alerts when data quality scores drop below configured thresholds.
    Currently supports: log-based alerts (extend for email/Slack/PagerDuty).
    """

    def __init__(self, threshold: float = 0.90, channels: list[str] | None = None) -> None:
        self.threshold = threshold
        self.channels = channels or ["log"]

    def check_and_alert(
        self, entity_type: str, quality_score: float, report: dict
    ) -> bool:
        """
        Check quality score against threshold; fire alert if below.

        Returns:
            True if alert was fired, False if quality passed.
        """
        if quality_score >= self.threshold:
            return False

        message = (
            f"⚠️  DATA QUALITY ALERT — {entity_type.upper()} | "
            f"Score={quality_score:.4f} (threshold={self.threshold}) | "
            f"Failed dimensions: {[k for k,v in report.get('dimensions',{}).items() if not v.get('passed')]}"
        )

        if "log" in self.channels:
            logger.warning(message)

        # Extend here for email/Slack/PagerDuty integrations
        # if "slack" in self.channels:
        #     self._send_slack(message)

        return True

    def _send_slack(self, message: str) -> None:
        """Placeholder for Slack webhook integration."""
        pass  # Implement with requests.post to SLACK_WEBHOOK_URL


class PerformanceProfiler:
    """
    Context manager that profiles a code block and logs results.
    Can also store metrics to metadata.pipeline_executions.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self._start = 0.0
        self.elapsed = 0.0

    def __enter__(self) -> "PerformanceProfiler":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_) -> None:
        self.elapsed = time.perf_counter() - self._start
        logger.debug("⏱  %s: %.4fs", self.label, self.elapsed)
