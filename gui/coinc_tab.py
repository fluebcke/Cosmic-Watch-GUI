"""
CoincidenceTab — GUI panel for two-detector coincidence data.

Plots:
  1. Instantaneous rates (master/slave/coincidence)  with legend
  2. Cumulative rates (master/slave/coincidence)     with 1/√N bands
  3. Δt distribution of coinc. pairs                 (orange histogram)
  4. Master ADC spectrum with coincident overlay     (blue)
  5. Slave ADC spectrum with coincident overlay      (red)
"""

import time
from collections import deque

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QCheckBox, QPushButton,
)
import pyqtgraph as pg

from session.coincidence import CoincidenceEvent

# Rate window constant
INSTANT_WINDOW_S  = 5
RATE_TICK_S       = 0.2
MAX_HISTORY_S     = 24 * 3600

# Rate display colors
_RATE_COLORS = {
    "master":      "#00CC55",  # green
    "slave":       "#DD3333",  # red
    "coincidence": "#FFCC00",  # yellow
}
_RATE_BRUSH = {
    "master":      (0, 204,  85, 160),
    "slave":       (221,  51,  51, 160),
    "coincidence": (255, 204,   0, 160),
}

# ── constants ─────────────────────────────────────────────────────────────────

COINC_RATE_WINDOW_S  = 30        # sliding window for coincidence rate curve
RATE_TICK_S          = 0.5       # how often rate curves are updated

ADC_MIN, ADC_MAX, ADC_BINS = 0, 1023, 64
ADC_BIN_W = (ADC_MAX - ADC_MIN) / ADC_BINS

DT_MIN_MS, DT_MAX_MS, DT_BINS = -50.0, 50.0, 100
DT_BIN_W = (DT_MAX_MS - DT_MIN_MS) / DT_BINS


def _plot(title: str, xlabel: str, ylabel: str, bg: str = "black") -> pg.PlotWidget:
    p = pg.PlotWidget()
    p.setBackground(bg)
    p.setTitle(title)
    p.setLabel("bottom", xlabel)
    p.setLabel("left",   ylabel)
    p.showGrid(x=True, y=True, alpha=0.2)
    return p


class CoincidenceTab(QWidget):

    def __init__(self):

        super().__init__()

        layout = QVBoxLayout()
        self.setLayout(layout)

        # ── summary labels ────────────────────────────────────────────────────

        hdr = QHBoxLayout()
        self._lbl_coinc  = QLabel("Coincidences: 0")
        self._lbl_frac   = QLabel("Fraction: —")
        self._lbl_anti   = QLabel("Anti-coinc: 0")
        for lbl in (self._lbl_coinc, self._lbl_frac, self._lbl_anti):
            lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
            hdr.addWidget(lbl)
        hdr.addStretch()
        layout.addLayout(hdr)

        # ── rate plots with legend ─────────────────────────────────────────────

        # Legend row
        legend_row = QHBoxLayout()
        for key, color in _RATE_COLORS.items():
            dot = QLabel(f"● {key.capitalize()}")
            dot.setStyleSheet(f"color:{color};font-size:10px;font-weight:bold;")
            legend_row.addWidget(dot)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        # Instantaneous rates plot
        inst_hdr = QHBoxLayout()
        inst_hdr.addWidget(QLabel(f"Instantaneous rates (last {INSTANT_WINDOW_S} s)"))
        inst_hdr.addStretch()
        layout.addLayout(inst_hdr)

        self._inst_plot = _plot("Instantaneous", "Time [s]", "Rate [Hz]")
        self._inst_plot.setLimits(xMin=0, yMin=0)
        self._inst_curves = {}
        for key, color in _RATE_COLORS.items():
            self._inst_curves[key] = self._inst_plot.plot(
                pen=pg.mkPen(color, width=2), name=key
            )
        layout.addWidget(self._inst_plot)

        # Cumulative rates plot with uncertainty bands
        cum_hdr = QHBoxLayout()
        cum_hdr.addWidget(QLabel("Cumulative rates"))
        cum_hdr.addStretch()
        reset_btn = QPushButton("Reset view")
        reset_btn.setFixedWidth(82)
        reset_btn.clicked.connect(self._reset_rate_view)
        cum_hdr.addWidget(reset_btn)
        layout.addLayout(cum_hdr)

        self._cum_plot = _plot("Cumulative", "Time [s]", "Rate [Hz]")
        self._cum_plot.setXLink(self._inst_plot)
        self._cum_curves = {}
        self._cum_upper = {}
        self._cum_lower = {}
        for key, color in _RATE_COLORS.items():
            # Upper and lower uncertainty bands
            rgba = _RATE_BRUSH[key]
            upper = self._cum_plot.plot(pen=pg.mkPen(color, width=1, alpha=80))
            lower = self._cum_plot.plot(pen=pg.mkPen(color, width=1, alpha=80))
            self._cum_plot.addItem(
                pg.FillBetweenItem(upper, lower, brush=pg.mkBrush(*rgba[:3], 30))
            )
            self._cum_upper[key] = upper
            self._cum_lower[key] = lower
            # Main curve
            self._cum_curves[key] = self._cum_plot.plot(
                pen=pg.mkPen(color, width=2), name=key
            )
        layout.addWidget(self._cum_plot)

        # ── 2×2 plot grid (ADC + delta-t) ─────────────────────────────────────

        grid = QGridLayout()
        layout.addLayout(grid)

        # — Δt distribution —
        self._dt_plot = _plot("Δt distribution (slave − master)", "Δt [ms]", "Counts")
        self._dt_plot.setLimits(yMin=0)
        self._dt_bin_centers = np.linspace(
            DT_MIN_MS + DT_BIN_W / 2, DT_MAX_MS - DT_BIN_W / 2, DT_BINS
        )
        self._dt_counts = np.zeros(DT_BINS, dtype=np.int64)
        self._dt_bars = pg.BarGraphItem(
            x=self._dt_bin_centers,
            height=self._dt_counts,
            width=DT_BIN_W * 0.9,
            brush="#F0A030",
        )
        self._dt_plot.addItem(self._dt_bars)
        # vertical line at Δt=0
        self._dt_plot.addItem(pg.InfiniteLine(
            pos=0, angle=90,
            pen=pg.mkPen("white", style=pg.QtCore.Qt.PenStyle.DashLine),
        ))
        grid.addWidget(self._dt_plot, 0, 1)

        # — master ADC spectrum —
        self._master_adc_plot = _plot("Master ADC spectrum", "ADC", "Counts")
        self._master_bins = np.zeros(ADC_BINS, dtype=np.int64)
        self._master_coinc_bins = np.zeros(ADC_BINS, dtype=np.int64)
        bin_x = [ADC_MIN + (i + 0.5) * ADC_BIN_W for i in range(ADC_BINS)]
        self._master_bars = pg.BarGraphItem(
            x=bin_x, height=self._master_bins,
            width=ADC_BIN_W * 0.9, brush="#378ADD",
        )
        self._master_coinc_bars = pg.BarGraphItem(
            x=bin_x, height=self._master_coinc_bins,
            width=ADC_BIN_W * 0.5, brush="yellow",
        )
        self._master_adc_plot.addItem(self._master_bars)
        self._master_adc_plot.addItem(self._master_coinc_bars)
        grid.addWidget(self._master_adc_plot, 1, 0)

        # — slave ADC spectrum —
        self._slave_adc_plot = _plot("Slave ADC spectrum", "ADC", "Counts")
        self._slave_bins = np.zeros(ADC_BINS, dtype=np.int64)
        self._slave_coinc_bins = np.zeros(ADC_BINS, dtype=np.int64)
        self._slave_bars = pg.BarGraphItem(
            x=bin_x, height=self._slave_bins,
            width=ADC_BIN_W * 0.9, brush="#E05555",
        )
        self._slave_coinc_bars = pg.BarGraphItem(
            x=bin_x, height=self._slave_coinc_bins,
            width=ADC_BIN_W * 0.5, brush="yellow",
        )
        self._slave_adc_plot.addItem(self._slave_bars)
        self._slave_adc_plot.addItem(self._slave_coinc_bars)
        grid.addWidget(self._slave_adc_plot, 1, 1)

        # ── controls below plots ──────────────────────────────────────────────

        ctrl = QHBoxLayout()
        self._coinc_overlay_cb = QCheckBox("Show coincident-only ADC overlay (yellow)")
        self._coinc_overlay_cb.setChecked(True)
        self._coinc_overlay_cb.toggled.connect(self._on_overlay_toggled)
        ctrl.addWidget(self._coinc_overlay_cb)
        ctrl.addStretch()

        reset_view_btn = QPushButton("Reset views")
        reset_view_btn.clicked.connect(self._reset_views)
        ctrl.addWidget(reset_view_btn)
        layout.addLayout(ctrl)

        # ── rate tracking state ───────────────────────────────────────────────
        self._instant_window = INSTANT_WINDOW_S
        self._rate_sources = {}  # key -> {ev_times, total, times, inst, cum, upper, lower}
        
        for key in _RATE_COLORS.keys():
            self._rate_sources[key] = {
                "ev_times": deque(),
                "total": 0,
                "times": [0.0],
                "inst": [0.0],
                "cum": [0.0],
                "upper": [0.0],
                "lower": [0.0],
            }

        self._start_time = time.monotonic()
        self._last_rate_tick = 0.0

        # ── ADC/coincidence state ──────────────────────────────────────────────
        self._coinc_times: deque[float] = deque()
        self._n_coinc = 0
        self._n_anti  = 0


    # ── public interface ──────────────────────────────────────────────────────

    def set_instant_window(self, seconds: int):
        """Change the sliding window for instantaneous rates."""
        self._instant_window = max(1, seconds)

    def on_master_event(self, event):
        """Call for every master event (matched or not)."""
        # Record for rate tracking
        now = time.monotonic()
        self._rate_sources["master"]["ev_times"].append(now)
        self._rate_sources["master"]["total"] += 1
        
        # ADC spectrum
        idx = int((event.adc - ADC_MIN) / ADC_BIN_W)
        if 0 <= idx < ADC_BINS:
            self._master_bins[idx] += 1
        self._master_bars.setOpts(height=self._master_bins.astype(float))

    def on_slave_event(self, event):
        """Call for every slave event (matched or not)."""
        # Record for rate tracking
        now = time.monotonic()
        self._rate_sources["slave"]["ev_times"].append(now)
        self._rate_sources["slave"]["total"] += 1
        
        # ADC spectrum
        idx = int((event.adc - ADC_MIN) / ADC_BIN_W)
        if 0 <= idx < ADC_BINS:
            self._slave_bins[idx] += 1
        self._slave_bars.setOpts(height=self._slave_bins.astype(float))

    def on_coincidence(self, coinc: CoincidenceEvent):
        """Call for each matched CoincidenceEvent."""
        now = time.monotonic()
        
        # Record for rate tracking
        self._rate_sources["coincidence"]["ev_times"].append(now)
        self._rate_sources["coincidence"]["total"] += 1
        
        # Coincidence tracking
        self._coinc_times.append(now)
        self._n_coinc += 1

        # Δt histogram
        dt = coinc.delta_t_ms
        if DT_MIN_MS <= dt <= DT_MAX_MS:
            idx = int((dt - DT_MIN_MS) / DT_BIN_W)
            idx = min(idx, DT_BINS - 1)
            self._dt_counts[idx] += 1
        self._dt_bars.setOpts(height=self._dt_counts.astype(float))

        # coincident-only ADC overlays
        for event, bins, bars in [
            (coinc.master, self._master_coinc_bins, self._master_coinc_bars),
            (coinc.slave,  self._slave_coinc_bins,  self._slave_coinc_bars),
        ]:
            idx = int((event.adc - ADC_MIN) / ADC_BIN_W)
            if 0 <= idx < ADC_BINS:
                bins[idx] += 1
            bars.setOpts(height=bins.astype(float))

    def update_totals(self, n_coinc: int, n_master: int, n_anti: int):
        """Update summary labels — call once per timer tick."""
        self._lbl_coinc.setText(f"Coincidences: {n_coinc:,}")
        self._n_anti = n_anti
        self._lbl_anti.setText(f"Anti-coinc: {n_anti:,}")
        frac = (n_coinc / n_master * 100) if n_master > 0 else 0.0
        self._lbl_frac.setText(f"Coinc. fraction: {frac:.2f} %")

    def _update_rate_plots(self):
        """Update instantaneous and cumulative rate plots with uncertainty bands."""
        now = time.monotonic()
        elapsed = now - self._start_time
        cut_hist = elapsed - MAX_HISTORY_S

        for key, s in self._rate_sources.items():
            # Trim instant window
            cut_inst = now - self._instant_window
            while s["ev_times"] and s["ev_times"][0] < cut_inst:
                s["ev_times"].popleft()

            # Compute rates
            inst = len(s["ev_times"]) / max(self._instant_window, 1e-6)
            cum = s["total"] / max(elapsed, 1e-6)
            sigma = (s["total"] ** 0.5) / max(elapsed, 1e-6)

            # Store data
            s["times"].append(elapsed)
            s["inst"].append(inst)
            s["cum"].append(cum)
            s["upper"].append(cum + sigma)
            s["lower"].append(max(cum - sigma, 0.0))

            # Trim history
            while s["times"] and s["times"][0] < cut_hist:
                for k in ("times", "inst", "cum", "upper", "lower"):
                    s[k].pop(0)

            # Update plots
            t = s["times"]
            self._inst_curves[key].setData(t, s["inst"])
            self._cum_curves[key].setData(t, s["cum"])
            self._cum_upper[key].setData(t, s["upper"])
            self._cum_lower[key].setData(t, s["lower"])

    def tick(self):
        """Update all plots — call on every GUI timer tick."""
        now = time.monotonic()
        if now - self._last_rate_tick < RATE_TICK_S:
            return
        self._last_rate_tick = now

        # Update rate plots (master, slave, coincidence)
        self._update_rate_plots()

        # Trim and update delta-t / ADC plots
        cutoff = now - COINC_RATE_WINDOW_S
        while self._coinc_times and self._coinc_times[0] < cutoff:
            self._coinc_times.popleft()

    def _reset_rate_view(self):
        """Reset rate plot view to auto-range."""
        self._inst_plot.enableAutoRange()
        self._cum_plot.enableAutoRange()

    def reset(self):
        """Reset all data and plots."""
        # Reset rate sources
        self._start_time = time.monotonic()
        self._last_rate_tick = 0.0
        for key in _RATE_COLORS.keys():
            s = self._rate_sources[key]
            s["ev_times"].clear()
            s["total"] = 0
            for k in ("times", "inst", "cum", "upper", "lower"):
                s[k] = [0.0]
            # Update plots with empty data
            self._inst_curves[key].setData([0.0], [0.0])
            self._cum_curves[key].setData([0.0], [0.0])
            self._cum_upper[key].setData([0.0], [0.0])
            self._cum_lower[key].setData([0.0], [0.0])

        # Reset coincidence tracking
        self._coinc_times.clear()
        self._n_coinc = 0
        self._n_anti  = 0

        self._dt_counts[:] = 0
        self._dt_bars.setOpts(height=self._dt_counts.astype(float))

        for arr, bars in [
            (self._master_bins,       self._master_bars),
            (self._master_coinc_bins, self._master_coinc_bars),
            (self._slave_bins,        self._slave_bars),
            (self._slave_coinc_bins,  self._slave_coinc_bars),
        ]:
            arr[:] = 0
            bars.setOpts(height=arr.astype(float))

        self._lbl_coinc.setText("Coincidences: 0")
        self._lbl_frac.setText("Fraction: —")
        self._lbl_anti.setText("Anti-coinc: 0")

    # ── internal ──────────────────────────────────────────────────────────────

    def _on_overlay_toggled(self, checked: bool):
        self._master_coinc_bars.setVisible(checked)
        self._slave_coinc_bars.setVisible(checked)

    def _reset_views(self):
        for plot in (self._rate_plot, self._dt_plot,
                     self._master_adc_plot, self._slave_adc_plot):
            plot.enableAutoRange()
