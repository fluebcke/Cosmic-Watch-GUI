import time
from collections import deque

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt


# -----------------
# shared style helpers
# -----------------

def _metric_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 16px; font-weight: bold;")
    return label


def _caption_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 10px; color: #888;")
    return label


def _format_duration(seconds: float) -> str:
    s = int(seconds)
    h, remainder = divmod(s, 3600)
    m, sec = divmod(remainder, 60)
    if h > 0:
        return f"{h} h {m:02d} min {sec:02d} s"
    if m > 0:
        return f"{m} min {sec:02d} s"
    return f"{sec} s"


# -----------------
# LiveStatsBar — a single horizontal row of metric tiles
# replacing the scattered event_label, rate_label, logging_status_label,
# HealthPanel, and RateCounterPanel.
#
# Tiles shown (left to right):
#   Events | Rate (30s) | Overall rate | Duration | Last packet | Logging
# -----------------

EVENT_TIMEOUT_S = 15.0


class _Tile(QFrame):
    """One metric tile: a large value label over a small caption."""

    def __init__(self, caption: str, initial: str = "—"):

        super().__init__()

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(110)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        self.setLayout(layout)

        self.value = QLabel(initial)
        self.value.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.caption = QLabel(caption)
        self.caption.setStyleSheet("font-size: 9px; color: #888;")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.value)
        layout.addWidget(self.caption)

    def set(self, text: str, color: str = ""):

        self.value.setText(text)
        style = "font-size: 15px; font-weight: bold;"
        if color:
            style += f" color: {color};"
        self.value.setStyleSheet(style)


class LiveStatsBar(QWidget):
    """Compact horizontal strip of live metric tiles.

    Fixed tiles (always shown):
      Events | Overall rate | Duration | Last packet | Logging

    Variable tiles (one per configured rate window, placed between Events
    and Overall rate):
      Rate (30 s) | Rate (1 min) | ...

    Call set_windows([30, 60, 300]) to change the variable tiles at any time.
    """

    _FIXED_WINDOW_S = None   # sentinel — the tile reads the configured window list

    def __init__(self, windows=None):

        super().__init__()

        self.setMaximumHeight(90)

        self._row = QHBoxLayout()
        self._row.setSpacing(4)
        self._row.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._row)

        # fixed tiles — always present
        self._t_events   = _Tile("Events",       "0")
        self._t_overall  = _Tile("Overall rate", "0.00 Hz")
        self._t_duration = _Tile("Duration",     "—")
        self._t_watchdog = _Tile("Last packet",  "—")
        self._t_logging  = _Tile("Logging",      "off")

        # variable rate-window tiles — rebuilt by set_windows()
        self._rate_tiles: list[tuple[int, _Tile]] = []   # (window_s, tile)

        # state
        self._connected        = False
        self._start_time: float | None = None
        self._last_event_time: float | None = None
        self._event_times: deque[float] = deque()
        self._total_events     = 0
        self._logging_active   = False
        self._max_window_s     = 30

        # build layout for the first time
        self.set_windows(windows or [30])


    # ── public interface ──────────────────────────────────────────────────────

    def set_windows(self, windows: list[int]):
        """Rebuild the variable rate tiles.  windows is a list of seconds."""

        # wipe the entire row and rebuild
        while self._row.count():
            item = self._row.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        self._rate_tiles = []
        self._max_window_s = max(windows) if windows else 30

        # trim event_times deque to new max window immediately
        now = _time_now = time.monotonic()
        cutoff = now - self._max_window_s
        while self._event_times and self._event_times[0] < cutoff:
            self._event_times.popleft()

        # ── layout: events | rate tiles... | overall | duration | watchdog | log
        self._row.addWidget(self._t_events)

        for w_s in windows:
            lbl = _seconds_label(w_s)
            tile = _Tile(f"Rate ({lbl})", "0.00 Hz")
            self._rate_tiles.append((w_s, tile))
            self._row.addWidget(tile)

        self._row.addWidget(self._t_overall)
        self._row.addWidget(self._t_duration)
        self._row.addWidget(self._t_watchdog)
        self._row.addWidget(self._t_logging)


    def set_connected(self, connected: bool):

        self._connected = connected

        if connected:
            self._start_time      = time.monotonic()
            self._last_event_time = None
            self._total_events    = 0
            self._event_times.clear()
        else:
            self._t_watchdog.set("—")
            self._t_duration.set("—")


    def set_logging_active(self, active: bool, path: str = ""):

        self._logging_active = active

        if active:
            self._t_logging.set("on", color="lightgreen")
            if path:
                self._t_logging.caption.setText(
                    path[-22:] if len(path) > 22 else path
                )
        else:
            self._t_logging.set("off")
            self._t_logging.caption.setText("Logging")


    def add_event(self, event):

        now = time.monotonic()
        self._event_times.append(now)
        self._total_events    += 1
        self._last_event_time  = now

        cutoff = now - self._max_window_s
        while self._event_times and self._event_times[0] < cutoff:
            self._event_times.popleft()

        self._t_events.set(f"{self._total_events:,}")


    def tick(self):

        now = time.monotonic()

        # variable rate windows
        for w_s, tile in self._rate_tiles:
            cutoff = now - w_s
            count  = sum(1 for t in self._event_times if t >= cutoff)
            tile.set(f"{count / w_s:.2f} Hz")

        # overall rate
        if self._start_time is not None and self._total_events > 0:
            elapsed = max(now - self._start_time, 1e-6)
            self._t_overall.set(f"{self._total_events / elapsed:.2f} Hz")

        # duration
        if self._connected and self._start_time is not None:
            self._t_duration.set(_format_duration(now - self._start_time))

        # last-packet watchdog
        if self._last_event_time is not None:
            since = now - self._last_event_time
            color = "red" if since > EVENT_TIMEOUT_S else ""
            self._t_watchdog.set(f"{since:.1f} s ago", color=color)


    def reset(self):

        self._total_events    = 0
        self._event_times.clear()
        self._last_event_time = None
        self._start_time      = time.monotonic() if self._connected else None

        self._t_events.set("0")
        self._t_overall.set("0.00 Hz")
        self._t_duration.set("0 s")
        self._t_watchdog.set("—")

        for _, tile in self._rate_tiles:
            tile.set("0.00 Hz")


def _seconds_label(seconds: int) -> str:
    """Compact human-readable label: '30 s', '1 min', '1 h'."""
    if seconds < 120:
        return f"{seconds} s"
    if seconds < 7200:
        m = seconds // 60
        return f"{m} min" if seconds % 60 == 0 else f"{seconds / 60:.1f} min"
    h = seconds // 3600
    return f"{h} h" if seconds % 3600 == 0 else f"{seconds / 3600:.1f} h"





# -----------------
# Event log table — used in the "Event Log" tab
# -----------------

MAX_LOG_ROWS = 300


class EventLogPanel(QWidget):

    def __init__(self):

        super().__init__()

        layout = QVBoxLayout()
        self.setLayout(layout)

        layout.addWidget(QLabel("Event log (most recent first)"))

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["#", "Time (ms)", "ADC", "Rate (Hz)", "Threshold (mV)"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        # clicking a column header sorts the table by that column
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)

        layout.addWidget(self.table)


    def add_event(self, event):
        # Temporarily disable sorting while inserting to avoid row thrashing
        self.table.setSortingEnabled(False)
        self.table.insertRow(0)

        def num_cell(value: float) -> QTableWidgetItem:
            """Cell that sorts numerically, not lexicographically."""
            item = QTableWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, value)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            return item

        self.table.setItem(0, 0, num_cell(event.evNum))
        self.table.setItem(0, 1, num_cell(event.time_ms))
        self.table.setItem(0, 2, num_cell(event.adc))
        self.table.setItem(0, 3, num_cell(round(event.rate, 4)))
        self.table.setItem(0, 4, num_cell(event.threshold))

        while self.table.rowCount() > MAX_LOG_ROWS:
            self.table.removeRow(self.table.rowCount() - 1)

        self.table.setSortingEnabled(True)


    def reset(self):

        self.table.setRowCount(0)
