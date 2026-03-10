"""Real-time monitoring service with live display."""

from __future__ import annotations

import logging
import signal
import time
from datetime import datetime

from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from sba.cli.display import render_edge_table, render_prop_table
from sba.config import get_settings
from sba.services.edge_finder import EdgeFinder
from sba.services.prop_analyzer import PropAnalyzer

logger = logging.getLogger(__name__)


class RealtimeMonitor:
    def __init__(self):
        self.settings = get_settings()
        self.edge_finder = EdgeFinder()
        self.prop_analyzer = PropAnalyzer()
        self._running = False

    def start(self, sport: str | None = None, interval: int | None = None,
              include_props: bool = True):
        """Start real-time monitoring loop with live display."""
        sport = sport or self.settings.DEFAULT_SPORT
        interval = interval or self.settings.REFRESH_INTERVAL_SECONDS
        self._running = True

        # Handle graceful shutdown
        def _stop(sig, frame):
            self._running = False
        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        with Live(self._build_layout("Starting...", [], []), refresh_per_second=1) as live:
            while self._running:
                try:
                    scan_time = datetime.now()

                    # Scan for edges
                    edges = self.edge_finder.scan(sport)
                    credits = self.edge_finder.credits_remaining()

                    # Scan props (if enabled and credits allow)
                    props = []
                    if include_props and (credits is None or credits > self.settings.ODDS_API_CREDIT_RESERVE):
                        try:
                            props = self.prop_analyzer.analyze(sport)
                        except Exception as e:
                            logger.warning(f"Prop scan failed: {e}")

                    # Update display
                    status = f"Last scan: {scan_time.strftime('%H:%M:%S')} | Credits: {credits or '?'} | Next: {interval}s"
                    live.update(self._build_layout(status, edges, props))

                    # Alert on high-value opportunities
                    for edge in edges:
                        if edge.ev >= 0.08:
                            print("\a", end="")  # Terminal bell
                            break

                except Exception as e:
                    logger.error(f"Scan error: {e}")
                    live.update(Panel(f"[red]Error: {e}[/red]", title="Monitor"))

                # Wait for next cycle
                for _ in range(interval):
                    if not self._running:
                        break
                    time.sleep(1)

    def stop(self):
        self._running = False

    def _build_layout(self, status: str, edges: list, props: list) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(Panel(Text(status), title="SBA Monitor"), size=3),
            Layout(name="main"),
        )

        if props:
            layout["main"].split_row(
                Layout(Panel(render_edge_table(edges), title=f"Edge Finder ({len(edges)} found)"), ratio=1),
                Layout(Panel(render_prop_table(props), title=f"Props ({len(props)} found)"), ratio=1),
            )
        else:
            layout["main"].update(
                Panel(render_edge_table(edges), title=f"Edge Finder ({len(edges)} found)")
            )

        return layout
