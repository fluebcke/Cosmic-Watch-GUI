"""
MainWindow — supports both single-detector and two-detector (coincidence) mode.

Single mode (slave_detector=None):
  - Toolbar shows port selector + Connect/Disconnect
  - Tabs: Live | Event Log

Coincidence mode (slave_detector provided):
  - Both detectors are already started by main.py before MainWindow is created
  - Toolbar hides the port/connect controls (connection is managed externally)
  - Tabs: Live | Coincidence | Event Log
"""

import csv

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QFileDialog, QSplitter,
)
from PyQt6.QtCore import QTimer, Qt

from .toolbar import Toolbar
from .plots import RatePanel, AdcHistogram
from .statusbar import StatusBar
from .widgets import LiveStatsBar, EventLogPanel
from .settings import SettingsDialog
from .logger import SessionLogger
from .coinc_tab import CoincidenceTab
#from .lifetime_tab import LifetimeTab


class MainWindow(QMainWindow):

    def __init__(self, detector, slave_detector=None):

        super().__init__()

        self.detector       = detector
        self.slave_detector = slave_detector
        self._coinc_mode    = slave_detector is not None

        # coincidence session — created lazily below if needed
        self._coinc_session = None
        if self._coinc_mode:
            from session.coincidence import CoincidenceSession
            self._coinc_session = CoincidenceSession(detector, slave_detector)

        self.logger = SessionLogger(base_dir="measurements")

        self._author_name = ""
        self._log_dir     = "measurements"
        self._all_events  = []          # master events (or only detector in single mode)

        title = (
            "Cosmic Watch — Coincidence Mode"
            if self._coinc_mode else
            "Cosmic Watch"
        )
        self.setWindowTitle(title)
        self.resize(1400, 850)


        # -----------------
        # Toolbar
        # -----------------

        self.toolbar = Toolbar(hide_connect=self._coinc_mode)
        self.addToolBar(self.toolbar)

        self.toolbar.threshold_changed.connect(self._on_threshold_changed)
        self.toolbar.logging_toggled.connect(self._on_logging_toggled)
        self.toolbar.restart_clicked.connect(self._on_restart)
        self.toolbar.settings_clicked.connect(self._on_settings)

        # single-mode only signals
        if not self._coinc_mode:
            self.toolbar.connect_clicked.connect(self._on_connect)
            self.toolbar.disconnect_clicked.connect(self._on_disconnect)
        else:
            # In coincidence mode, disable measurement controls
            self.toolbar.set_coincidence_mode(True)


        # -----------------
        # Status bar
        # -----------------

        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)


        # -----------------
        # Tabs
        # -----------------

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tabs.addTab(self._build_live_tab(), "Live")

        #if self._coinc_mode:
            #self.coinc_tab = CoincidenceTab()
            #self.tabs.addTab(self.coinc_tab, "Coincidence")
            
            #self.lifetime_tab = LifetimeTab()
            #self.tabs.addTab(self.lifetime_tab, "Lifetime & Velocity")

        self.tabs.addTab(self._build_event_log_tab(), "Event Log")


        # -----------------
        # In coincidence mode both detectors are already running — mark
        # the toolbar/stats as connected immediately.
        # -----------------

        if self._coinc_mode:
            try:
                self._coinc_session.start()
            except Exception as exc:
                # Show the error after the window is visible (timer hasn't
                # started yet, so we queue it via the status bar directly)
                self.status_bar.show_response(
                    f"Could not start detectors: {exc} — replug and restart."
                )
            else:
                port_label = f"{detector.port} + {slave_detector.port}"
                self.toolbar.set_connected(True)
                self.toolbar.logging_btn.setEnabled(True)
                self.status_bar.set_connected(True, port_label)
                self.live_stats.set_connected(True)
                self.toolbar.set_logging_active(False)


        # -----------------
        # GUI update timer
        # -----------------

        self.timer = QTimer()
        self.timer.timeout.connect(self._update_data)
        self.timer.start(100)


    # ── tab builders ──────────────────────────────────────────────────────────

    def _build_live_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QSplitter
        page   = QWidget()
        outer  = QVBoxLayout()
        page.setLayout(outer)

        # stats bar spans full width at the top
        self.live_stats = LiveStatsBar()
        outer.addWidget(self.live_stats)

        # vertical splitter: rate panel (top, larger) | ADC histogram (bottom, narrower)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        self.rate_panel = RatePanel()
        splitter.addWidget(self.rate_panel)

        self.adc_histogram = AdcHistogram()
        splitter.addWidget(self.adc_histogram)

        # rate panel gets 60% of horizontal space, ADC 40%
        total = 1000
        splitter.setSizes([600, 400])

        return page


    def _build_event_log_tab(self) -> QWidget:

        page = QWidget()
        layout = QVBoxLayout()
        page.setLayout(layout)

        top_row = QHBoxLayout()
        top_row.addStretch()
        export_btn = QPushButton("Export CSV...")
        export_btn.clicked.connect(self._on_export_csv)
        top_row.addWidget(export_btn)
        layout.addLayout(top_row)

        self.event_log_panel = EventLogPanel()
        layout.addWidget(self.event_log_panel)

        return page


    # ── single-mode connection handling ───────────────────────────────────────

    def _on_connect(self, port):

        try:
            self.detector.port = port
            self.detector.start()
            self.detector.start_measurement()
        except Exception as exc:
            # Port exists but hardware isn't ready — show the error in the
            # status bar and leave everything in disconnected state so the
            # user can retry without restarting the app.
            self.toolbar.set_connected(False)
            self.status_bar.set_connected(False)
            self.status_bar.show_response(
                f"Could not open {port}: {exc} — replug the Pico and try again."
            )
            # make sure the reader thread isn't left half-started
            try:
                self.detector.stop()
            except Exception:
                pass
            return

        self.toolbar.set_connected(True)
        self.toolbar.logging_btn.setEnabled(True)
        self.status_bar.set_connected(True, port)
        self.live_stats.set_connected(True)

        if not self.timer.isActive():
            self.timer.start(100)


    def _on_disconnect(self):

        if self.logger.active:
            self.logger.stop()
            self.toolbar.set_logging_active(False)
            self.live_stats.set_logging_active(False)

        self.detector.stop()

        self.toolbar.set_connected(False)
        self.status_bar.set_connected(False)
        self.live_stats.set_connected(False)


    # ── toolbar callbacks (both modes) ────────────────────────────────────────

    def _on_threshold_changed(self, value):

        self.detector.set_threshold(value)
        if self._coinc_mode and self.slave_detector:
            self.slave_detector.set_threshold(value)
        self.adc_histogram.set_threshold(value)


    def _on_logging_toggled(self, start: bool):

        if start:
            port = (
                f"{self.detector.port}+{self.slave_detector.port}"
                if self._coinc_mode else
                self.detector.port
            )
            path = self.logger.start(
                port      = port,
                baud      = self.detector.baud,
                threshold = self.toolbar.threshold_spin.value(),
                author    = self._author_name or "(unset)",
            )
            self.toolbar.set_logging_active(True)
            self.live_stats.set_logging_active(True, path)
        else:
            self.logger.stop()
            self.toolbar.set_logging_active(False)
            self.live_stats.set_logging_active(False)


    def _on_restart(self):

        if self._coinc_mode:
            self._coinc_session.master.reset()
            self._coinc_session.slave.reset()
            self._coinc_session.master.start_measurement()
            self._coinc_session.slave.start_measurement()
            if hasattr(self, "coinc_tab"):
                self.coinc_tab.reset()
            if hasattr(self, "lifetime_tab"):
                self.lifetime_tab.reset()
        else:
            self.detector.reset()
            self.detector.start_measurement()

        self.rate_panel.reset()
        self.adc_histogram.reset()
        self.live_stats.reset()
        self.event_log_panel.reset()
        self._all_events = []


    def _on_settings(self):

        dialog = SettingsDialog(
            self,
            current_name        = self._author_name,
            current_log_dir     = self._log_dir,
            current_windows     = [w for w, _ in self.live_stats._rate_tiles] or [30],
            current_live_rate   = self.rate_panel._instant_window,
        )

        if dialog.exec():
            values = dialog.values()

            # Apply author name to detectors
            self._author_name = values["name"]
            if self._author_name:
                self.detector.set_name(self._author_name)
                if self._coinc_mode and self.slave_detector:
                    self.slave_detector.set_name(self._author_name)

            # Apply log directory
            self._log_dir        = values["log_dir"]
            self.logger.base_dir = self._log_dir

            # Apply live rate window
            live_rate = values.get("live_rate_window", 5)
            self.rate_panel.set_instant_window(live_rate)
            if self._coinc_mode and hasattr(self, 'coinc_tab'):
                self.coinc_tab.set_instant_window(live_rate)

            # Rebuild the rate window tiles in the stats bar
            new_windows = values["rate_windows"]
            if new_windows:
                self.live_stats.set_windows(new_windows)


    def _on_export_csv(self):

        if not self._all_events:
            self.status_bar.show_response("Nothing to export — no events recorded.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export events as CSV", "events.csv", "CSV files (*.csv)"
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["evNum", "time_ms", "adc", "rate", "threshold"])
            for ev in self._all_events:
                writer.writerow([ev.evNum, ev.time_ms, ev.adc, ev.rate, ev.threshold])

        self.status_bar.show_response(f"Exported {len(self._all_events)} events to {path}")


    # ── live update loop ──────────────────────────────────────────────────────

    def _update_data(self):

        self.rate_panel.tick()
        self.live_stats.tick()

        if self._coinc_mode:
            self._update_coinc()
        else:
            self._update_single()


    def _update_single(self):
        """Drain the single detector queue."""

        while not self.detector.queue.empty():
            event = self.detector.queue.get()
            self._dispatch_event(event)

        self._drain_responses(self.detector)


    def _update_coinc(self):
        """Call CoincidenceSession.process() and dispatch results to all panels."""

        master_events, slave_events, coincidences = self._coinc_session.process()

        for event in master_events:
            self._dispatch_event(event)
            self.coinc_tab.on_master_event(event)

        for event in slave_events:
            self.coinc_tab.on_slave_event(event)

        for coinc in coincidences:
            self.coinc_tab.on_coincidence(coinc)
            self.lifetime_tab.add_coincidence(coinc)

        self.coinc_tab.tick()
        self.lifetime_tab.tick()
        self.coinc_tab.update_totals(
            n_coinc  = self._coinc_session.n_coincidences,
            n_master = self._coinc_session.n_master,
            n_anti   = self._coinc_session.n_anti,
        )

        # drain response queues from both detectors
        self._drain_responses(self.detector)
        self._drain_responses(self.slave_detector)


    def _dispatch_event(self, event):
        """Send one master/single event to all single-detector panels."""

        self.rate_panel.add_event(event)
        self.adc_histogram.add_event(event)
        self.live_stats.add_event(event)
        self.event_log_panel.add_event(event)
        self._all_events.append(event)

        if self.logger.active:
            self.logger.write_event(event)


    def _drain_responses(self, detector):
        """Drain command-response queue for one detector, handle connection loss."""

        while not detector.responses.empty():
            line = detector.responses.get()

            if line.startswith("CONNECTION_LOST:"):
                if self.logger.active:
                    self.logger.stop()
                    self.toolbar.set_logging_active(False)
                    self.live_stats.set_logging_active(False)

                self.toolbar.set_connected(False)
                self.status_bar.set_connected(False)
                self.live_stats.set_connected(False)
                self.status_bar.show_response(
                    f"[{detector.port}] {line}"
                )
                self.timer.stop()
                return

            self.status_bar.show_response(line)


    # ── window close ──────────────────────────────────────────────────────────

    def closeEvent(self, event):

        if self.logger.active:
            self.logger.stop()

        if self._coinc_mode:
            self._coinc_session.stop()
        elif self.detector.connected:
            self.detector.stop()

        super().closeEvent(event)
