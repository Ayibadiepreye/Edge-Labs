"""Edge Labs — Background Account Telemetry Poller
Periodically refreshes balance, equity, and margin stats for all active accounts with anti-Cloudflare jitter.
Runs independently to avoid interfering with high-speed tick analysis.
"""
import time
import random
import logging
import threading
from typing import Callable, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from core.multi_account_manager import MultiAccountManager
import config

logger = logging.getLogger("system")


class TelemetrySignals(QObject):
    telemetry_updated = pyqtSignal(dict)  # Emits {acc_id: telemetry_dict}
    circuit_breaker_alert = pyqtSignal(str, str)  # Emits (account_name, reason)


class TelemetryPoller:
    """Daemon thread for jittered account telemetry polling and circuit breaker enforcement."""

    def __init__(self, account_manager: MultiAccountManager):
        self.account_manager = account_manager
        self.signals = TelemetrySignals()
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.interval_sec = config.TELEMETRY_POLL_INTERVAL_SEC

    def start(self):
        """Starts the background telemetry polling thread."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, name="TelemetryPollerThread", daemon=True)
        self._thread.start()
        logger.info("Background Telemetry Poller started (Interval: ~5 min with jitter).")

    def stop(self):
        """Stops the telemetry poller."""
        self.running = False

    def _run_loop(self):
        # Initial poll after 5 seconds
        time.sleep(5.0)
        while self.running:
            try:
                self.poll_now()
            except Exception as e:
                logger.warning(f"Telemetry poll encountered error: {e}")

            # Sleep with random jitter (e.g. 300s +/- 30s) to avoid bot detection
            jitter = random.uniform(-30.0, 30.0)
            sleep_time = max(120.0, self.interval_sec + jitter)
            
            # Sleep in small 1-second chunks for responsive shutdown
            slept = 0.0
            while self.running and slept < sleep_time:
                time.sleep(1.0)
                slept += 1.0

    def poll_now(self) -> dict:
        """Executes an immediate telemetry poll across all accounts."""
        all_stats = {}
        for acc_id in list(self.account_manager.accounts.keys()):
            stats = self.account_manager.refresh_account_telemetry(acc_id)
            if stats:
                all_stats[acc_id] = stats
                if stats.get("circuit_breaker_tripped"):
                    self.signals.circuit_breaker_alert.emit(
                        stats["account_name"],
                        f"Daily Drawdown Limit of {stats['daily_loss_floor']} reached!"
                    )

        if all_stats:
            self.signals.telemetry_updated.emit(all_stats)
        return all_stats
