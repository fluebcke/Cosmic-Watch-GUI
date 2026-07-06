"""
plots.py — all plot widgets for the Cosmic Watch GUI.

RatePanel       single-detector: instantaneous + cumulative rate, 1/√N band
AdcHistogram    pulse-height spectrum: configurable bins, log scale, fitting
DualRatePanel   coincidence tab: master / slave / coincidence on shared axes
"""

import time
from collections import deque

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QSpinBox, QComboBox, QLineEdit, QMainWindow,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer

import pyqtgraph as pg


# ═══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════════

class NiceRateAxisItem(pg.AxisItem):
    """Y-axis for rate plots that rounds tick values to even numbers.

    pyqtgraph's default auto-ticks can produce values like 0.83 Hz or 1.7 Hz.
    This axis snaps major tick spacing to the nearest 'nice' value
    (1, 2, 5, 10, 20, 50, 100, …) so labels always read 0, 1, 2 or 0, 2, 4 etc.
    """

    _NICE = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]

    def tickValues(self, minVal, maxVal, size):
        span = maxVal - minVal
        if span <= 0:
            return []
        # target ~5 ticks
        raw_step = span / 5.0
        step = next((n for n in self._NICE if n >= raw_step), self._NICE[-1])
        start = (int(minVal / step)) * step
        ticks = []
        v = start
        while v <= maxVal + step:
            if v >= minVal - 1e-9:
                ticks.append(v)
            v = round(v + step, 10)
        return [(step, ticks)]

    def tickStrings(self, values, scale, spacing):
        return [f"{v:.0f}" if v == int(v) else f"{v:.2f}" for v in values]


class TimeAxisItem(pg.AxisItem):
    """Tick labels that switch between s / min / h as the visible range grows."""

    def tickStrings(self, values, scale, spacing):
        if not values:
            return []
        max_val = max(abs(v) for v in values)
        if max_val < 120:
            unit, divisor, fmt = "s", 1, "{:.0f}"
        elif max_val < 7200:
            unit, divisor, fmt = "min", 60, "{:.1f}"
        else:
            unit, divisor, fmt = "h", 3600, "{:.2f}"
        self.setLabel(f"Time [{unit}]")
        return [fmt.format(v / divisor) for v in values]


def _base_plot(y_label: str = "Rate [Hz]", time_axis: bool = True) -> pg.PlotWidget:
    """Consistently styled dark PlotWidget factory."""
    kw = {"axisItems": {
        "bottom": TimeAxisItem(orientation="bottom") if time_axis else pg.AxisItem("bottom"),
        "left":   NiceRateAxisItem(orientation="left"),
    }}
    p = pg.PlotWidget(**kw)
    p.setBackground("white")
    
    # FORCE dark-text axis styling (fix grey labels)
    p.getAxis("left").setTextPen("black")
    p.getAxis("bottom").setTextPen("black")
    p.getAxis("left").setPen(pg.mkPen("black"))
    p.getAxis("bottom").setPen(pg.mkPen("black"))
    
    p.setLabel("left", y_label)
    p.showGrid(x=True, y=True, alpha=0.35)
    p.setLimits(xMin=0, yMin=0)
    p.enableAutoRange()
    return p


# ─── Fullscreen window ────────────────────────────────────────────────────────

class _FullScreenWindow(QMainWindow):
    """Standalone maximised window showing a live-refreshed copy of a plot.

    Rather than moving the original widget (which breaks Qt ownership), this
    creates new PlotDataItems / ScatterPlotItems in a fresh PlotWidget and
    refreshes them from the source panel's data lists every 200 ms.  Because
    Python lists are reference types, any append to the original list is
    immediately visible here with no signalling needed.
    """

    def __init__(self, title: str, y_label: str = "Rate [Hz]",
                 time_axis: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{title} — Full Screen")
        self.showMaximized()

        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout()
        central.setLayout(lay)

        note = QLabel("Live view   ·   close this window to return")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet("color:#555; font-size:10px;")
        lay.addWidget(note)

        self.plot = _base_plot(y_label, time_axis)
        lay.addWidget(self.plot)

        self._line_items:    dict[str, pg.PlotDataItem]   = {}
        self._scatter_items: dict[str, pg.ScatterPlotItem] = {}
        self._fill_items:    dict[str, pg.FillBetweenItem] = {}
        self._data_fns:      list = []   # each fn() → dict[name → (x,y)]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(200)

    def add_line(self, name: str, pen, name_scatter: str | None = None,
                 scatter_brush=None):
        item = self.plot.plot(pen=pen, name=name)
        self._line_items[name] = item
        if name_scatter and scatter_brush:
            sc = pg.ScatterPlotItem(size=5, pen=pg.mkPen(None), brush=scatter_brush)
            self.plot.addItem(sc)
            self._scatter_items[name_scatter] = sc

    def add_fill(self, name: str, upper_name: str, lower_name: str, brush):
        upper = self.plot.plot(pen=pg.mkPen(None))
        lower = self.plot.plot(pen=pg.mkPen(None))
        fill  = pg.FillBetweenItem(upper, lower, brush=pg.mkBrush(brush))
        self.plot.addItem(fill)
        self._line_items[upper_name] = upper
        self._line_items[lower_name] = lower
        self._fill_items[name]       = fill

    def register(self, fn):
        """fn() must return dict of name → (x_list, y_list)."""
        self._data_fns.append(fn)

    def _refresh(self):
        for fn in self._data_fns:
            try:
                data = fn()
            except Exception:
                continue
            for name, (x, y) in data.items():
                x, y = list(x), list(y)
                if name in self._line_items:
                    self._line_items[name].setData(x, y)
                if name in self._scatter_items:
                    n = min(len(x), 200)
                    self._scatter_items[name].setData(x[-n:], y[-n:])

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


def _fs_button(plot: pg.PlotWidget, open_fn) -> QPushButton:
    """Small semi-transparent ⤢ button pinned to the top-right corner of *plot*."""
    btn = QPushButton("⤢", plot)
    btn.setFixedSize(22, 22)
    btn.setToolTip("Open in full screen")
    btn.setStyleSheet(
        "QPushButton{background:rgba(70,70,70,130);color:#ddd;"
        "border:none;border-radius:3px;font-size:12px;}"
        "QPushButton:hover{background:rgba(110,110,110,180);}"
    )
    btn.clicked.connect(open_fn)

    original_resize = plot.resizeEvent

    def _resize(ev):
        original_resize(ev)
        btn.move(plot.width() - btn.width() - 4, 4)

    plot.resizeEvent = _resize
    btn.move(plot.width() - btn.width() - 4, 4)
    return btn

from scipy import stats as sp_stats

def _bayesian_rate_interval(N, t, prior_rate=1.0, conf=0.95):
    if t <= 0:
        return (0.0, 0.0, 0.0)

    alpha0 = 1.0
    beta0 = 1.0 / prior_rate

    alpha = alpha0 + N
    beta = beta0 + t

    lower_q = (1 - conf) / 2
    upper_q = 1 - lower_q

    lower = sp_stats.gamma.ppf(lower_q, a=alpha, scale=1/beta)
    upper = sp_stats.gamma.ppf(upper_q, a=alpha, scale=1/beta)
    mean = alpha / beta

    return float(lower), float(mean), float(upper)

# ═══════════════════════════════════════════════════════════════════════════════
# RatePanel
# ═══════════════════════════════════════════════════════════════════════════════

INSTANT_WINDOW_S = 5       # default live-rate window in seconds
RATE_TICK_S      = 0.2
MAX_HISTORY_S    = 24 * 3600

_BAND_BRUSH = (170, 170, 170, 50)      # light gray
_BAND_PEN   = pg.mkPen((130, 130, 130, 140), width=1)

class RatePanel(QWidget):
    """Instantaneous (30 s) + cumulative rate with continuous 1/√N uncertainty band."""
    
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        self.setLayout(layout)

        self._instant_window = INSTANT_WINDOW_S   # adjustable at runtime
        self._scroll_mode = False
        self._display_span = 60

        # Display mode for the x-axis
        self._scroll_mode = False          # False = entire measurement
        self._display_span = 60            # seconds shown when scrolling

        self._scroll_cb = QCheckBox("Scrolling window")
        self._scroll_cb.setChecked(False)
        self._scroll_cb.toggled.connect(self._on_scroll_mode_changed)
        self._span_spin = QSpinBox()
        self._span_spin.setRange(10, 3600)
        self._span_spin.setValue(60)
        self._span_spin.setSuffix(" s")
        self._span_spin.valueChanged.connect(self._on_display_span_changed)

        # ── instantaneous ─────────────────────────────────────────────────────

        ih = QHBoxLayout()

        self._instant_label = QLabel(f"Rate (last {self._instant_window} s)")
        ih.addWidget(self._instant_label)

        # ── NEW CONTROLS START HERE ─────────────────────────────
        self._scroll_cb.setChecked(False)
        self._scroll_cb.toggled.connect(self._on_scroll_mode_changed)

        self._span_spin.setRange(10, 3600)
        self._span_spin.setValue(60)
        self._span_spin.setSuffix(" s")
        self._span_spin.valueChanged.connect(self._on_display_span_changed)

        ih.addWidget(self._scroll_cb)
        ih.addWidget(QLabel("Span"))
        ih.addWidget(self._span_spin)
        # ── NEW CONTROLS END HERE ───────────────────────────────

        ih.addStretch()
        layout.addLayout(ih)

        self.instant_plot = _base_plot()
        self.instant_curve = self.instant_plot.plot(pen=pg.mkPen("#1f77b4", width=2))
        # Average rate (dashed red line)
        self.mean_curve = self.instant_plot.plot(
            pen=pg.mkPen("#d62728", width=2, style=Qt.PenStyle.DashLine)        )

        _fs_button(self.instant_plot, self._open_instant_fs)
        layout.addWidget(self.instant_plot)

        # ── cumulative ────────────────────────────────────────────────────────

        ch = QHBoxLayout()
        ch.addWidget(QLabel("Cumulative rate (since start)"))
        ch.addStretch()
        self._band_cb = QCheckBox("uncertainty band")
        self._band_cb.setChecked(True)
        self._band_cb.toggled.connect(self._on_band_toggled)
        ch.addWidget(self._band_cb)
        reset_btn = QPushButton("Reset view")
        reset_btn.setFixedWidth(82)
        reset_btn.clicked.connect(self._reset_view)
        ch.addWidget(reset_btn)
        layout.addLayout(ch)

        self.cumulative_plot = _base_plot()
        self.cumulative_plot.setXLink(self.instant_plot)

        # Band curves first (bottom z-order), rate line on top
        self._upper = self.cumulative_plot.plot(pen=_BAND_PEN)
        self._lower = self.cumulative_plot.plot(pen=_BAND_PEN)
        self._band  = pg.FillBetweenItem(
            self._upper, self._lower, brush=pg.mkBrush(_BAND_BRUSH))
        self.cumulative_plot.addItem(self._band)
        self.cumulative_curve = self.cumulative_plot.plot(pen=pg.mkPen("#d62728", width=2))

        _fs_button(self.cumulative_plot, self._open_cumulative_fs)
        layout.addWidget(self.cumulative_plot)
        
        stats_row = QHBoxLayout()
        stats_row.addWidget(QLabel("Statistics (instant window):"))

        self._stat_mean_label = QLabel("Mean: —")
        self._stat_mean_label.setStyleSheet("font-size: 10px; color: #888;")

        self._stat_median_label = QLabel("Median: —")
        self._stat_median_label.setStyleSheet("font-size: 10px; color: #888;")

        self._stat_stddev_label = QLabel("StdDev: —")
        self._stat_stddev_label.setStyleSheet("font-size: 10px; color: #888;")

        stats_row.addWidget(self._stat_mean_label)
        stats_row.addWidget(self._stat_median_label)
        stats_row.addWidget(self._stat_stddev_label)
        stats_row.addStretch()

        layout.addLayout(stats_row)

        # ── state ─────────────────────────────────────────────────────────────

        self._event_times:      deque[float] = deque()
        self._total_events      = 0

        self._times:     list[float] = [0.0]
        self._instant:   list[float] = [0.0]
        self._cumul:     list[float] = [0.0]
        self._upper_r:   list[float] = [0.0]
        self._lower_r:   list[float] = [0.0]

        self._start_time = time.monotonic()
        self._last_tick  = 0.0

        self._fs_instant:    _FullScreenWindow | None = None
        self._fs_cumulative: _FullScreenWindow | None = None

        self._draw()

    # ── public ────────────────────────────────────────────────────────────────

    def set_instant_window(self, seconds: int):
        """Change the sliding window used for the instantaneous rate curve."""
        self._instant_window = max(1, seconds)
        self._instant_label.setText(f"Rate (last {self._instant_window} s)")

    def add_event(self, event):
        now = time.monotonic()
        self._event_times.append(now)
        self._total_events += 1
        cutoff = now - self._instant_window
        while self._event_times and self._event_times[0] < cutoff:
            self._event_times.popleft()

    def tick(self):
        now = time.monotonic()
        if now - self._last_tick < RATE_TICK_S:
            return
        self._last_tick = now

        cutoff = now - self._instant_window
        while self._event_times and self._event_times[0] < cutoff:
            self._event_times.popleft()

        elapsed = now - self._start_time
        N_i     = self._total_events                  # events accumulated so far
        t_i     = max(elapsed, 1e-6)

        # R_i = N_i / t_i   (cumulative rate at this sample)
        # σ_i = √N_i / t_i  (Poisson uncertainty: δN = √N → δR = √N/t)
        inst  = len(self._event_times) / self._instant_window
        cum   = N_i / t_i
        cum_lower, cum_mean, cum_upper = _bayesian_rate_interval(
            N=N_i,
            t=t_i,
            prior_rate=1.0,
            conf=0.95
        )
        
        self._times.append(elapsed)
        self._instant.append(inst)
        # ── STATISTICS (instant window) ───────────────────────────────
        if len(self._instant) > 5:
            # number of samples corresponding to window duration
            window_n = max(1, int(self._instant_window / RATE_TICK_S))

            recent = self._instant[-window_n:]

            mean_rate   = float(np.mean(recent))
            median_rate = float(np.median(recent))
            std_rate    = float(np.std(recent))

            self._stat_mean_label.setText(f"Mean: {mean_rate:.3f} Hz")
            self._stat_median_label.setText(f"Median: {median_rate:.3f} Hz")
            self._stat_stddev_label.setText(f"StdDev: {std_rate:.3f} Hz")
        self._cumul.append(cum_mean)
        self._upper_r.append(cum_upper)
        self._lower_r.append(cum_lower) 

        cut = elapsed - MAX_HISTORY_S
        while self._times and self._times[0] < cut:
            for lst in (self._times, self._instant, self._cumul,
                        self._upper_r, self._lower_r):
                lst.pop(0)

        self._draw()

    def reset(self):
        self._event_times.clear()
        self._total_events = 0
        self._times    = [0.0]
        self._instant  = [0.0]
        self._cumul    = [0.0]
        self._upper_r  = [0.0]
        self._lower_r  = [0.0]
        self._start_time = time.monotonic()
        self._last_tick  = 0.0
        self._draw()

    # ── internal ──────────────────────────────────────────────────────────────

    def _draw(self):
        t = self._times
        if self._scroll_mode:
            cutoff = self._times[-1] - self._display_span
            start = 0
            while start < len(self._times) and self._times[start] < cutoff:
                start += 1
            x = self._times[start:]
            y = self._instant[start:]
        else:
            x = self._times
            y = self._instant
        t = self._times
        if self._scroll_mode and len(t):
            cutoff = t[-1] - self._display_span
            start = 0
            while start < len(t) and t[start] < cutoff:
                start += 1
            x = t[start:]
            y = self._instant[start:]
        else:
            x = t
            y = self._instant
        self.instant_curve.setData(x, y)
        if len(y):
            mean = np.mean(y)
            self.mean_curve.setData(x,[mean] * len(x))
        if self._scroll_mode and len(x):
            self.instant_plot.setXRange(
                max(0, x[-1] - self._display_span),
                x[-1],padding=0)
        else:
            self.instant_plot.enableAutoRange(axis="x")
        self.cumulative_curve.setData(t, self._cumul)
        if self._band_cb.isChecked():
            self._upper.setData(t, self._upper_r)
            self._lower.setData(t, self._lower_r)
        if self._scroll_mode and len(x):
            self.instant_plot.setXRange(max(0, x[-1] - self._display_span),x[-1],padding=0)
        else:
            self.instant_plot.enableAutoRange(axis="x")

    def _on_band_toggled(self, checked: bool):
        t = self._times
        if checked:
            self._upper.setData(t, self._upper_r)
            self._lower.setData(t, self._lower_r)
        else:
            self._upper.setData(t, self._cumul)
            self._lower.setData(t, self._cumul)

    def _reset_view(self):
        self.instant_plot.enableAutoRange()
        self.cumulative_plot.enableAutoRange()

    def _open_instant_fs(self):
        if self._fs_instant and not self._fs_instant.isHidden():
            self._fs_instant.activateWindow()
            return
        win = _FullScreenWindow("Instantaneous rate", "Rate [Hz]")
        win.add_line("line", pg.mkPen("#1f77b4", width=2))
        win.register(lambda: {"line": (self._times, self._instant)})
        self._fs_instant = win
        win.show()

    def _open_cumulative_fs(self):
        if self._fs_cumulative and not self._fs_cumulative.isHidden():
            self._fs_cumulative.activateWindow()
            return
        win = _FullScreenWindow("Cumulative rate", "Rate [Hz]")
        win.add_fill("band", "upper", "lower", _BAND_BRUSH)
        win.add_line("line", pg.mkPen("#d62728", width=2))
        win.register(lambda: {
            "upper": (self._times, self._upper_r),
            "lower": (self._times, self._lower_r),
            "line":  (self._times, self._cumul),
        })
        self._fs_cumulative = win
        win.show()
        
    def _on_scroll_mode_changed(self, checked: bool):
        self._scroll_mode = checked
        self._draw()

    def _on_display_span_changed(self, value: int):
        self._display_span = value
        self._draw()


# ═══════════════════════════════════════════════════════════════════════════════
# AdcHistogram
# ═══════════════════════════════════════════════════════════════════════════════

ADC_MIN  = 0
ADC_MAX  = 1023
_DEFAULT_BIN_WIDTH  = 16
_MIN_EVENTS_FOR_FIT = 100


def _exp_model(x, a, b):
    return a * np.exp(-b * x)

def _power_model(x, a, b):
    return a * np.power(np.maximum(x, 1e-6), -b)

_FIT_MODELS = {
    "Exponential  a·e^(−b·x)":         (_exp_model,   ["a", "b"]),
    "Power law    a·x^(−b)":            (_power_model, ["a", "b"]),
   }


class AdcHistogram(QWidget):

    def __init__(self):
        super().__init__()
        self._log_mode = False

        outer = QVBoxLayout()
        self.setLayout(outer)

        # ── header ────────────────────────────────────────────────────────────

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("ADC pulse-height spectrum"))
        hdr.addStretch()

        hdr.addWidget(QLabel("Bin:"))
        self._bin_spin = QSpinBox()
        self._bin_spin.setRange(1, 256)
        self._bin_spin.setValue(_DEFAULT_BIN_WIDTH)
        self._bin_spin.setSuffix(" ADC")
        self._bin_spin.setFixedWidth(80)
        self._bin_spin.editingFinished.connect(self._rebuild)
        hdr.addWidget(self._bin_spin)

        self._log_cb = QCheckBox("Log")
        self._log_cb.toggled.connect(self._on_log_toggled)
        hdr.addWidget(self._log_cb)

        outer.addLayout(hdr)

        # ── plot ──────────────────────────────────────────────────────────────

        self.plot = pg.PlotWidget()
        self.plot.setBackground("white")
        self.plot.getAxis("left").setTextPen("black")
        self.plot.getAxis("bottom").setTextPen("black")
        self.plot.getAxis("left").setPen(pg.mkPen("black"))
        self.plot.getAxis("bottom").setPen(pg.mkPen("black"))
        self.plot.setLabel("bottom", "ADC value")
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setLimits(yMin=0)
        self.plot.getViewBox().setMouseMode(pg.ViewBox.PanMode)

        self._bars:       pg.BarGraphItem | None = None
        self._fit_curve:  pg.PlotDataItem  | None = None
        self.threshold_line = pg.InfiniteLine(
            pos=150, angle=90,
            pen=pg.mkPen("red", style=pg.QtCore.Qt.PenStyle.DashLine),
        )
        _fs_button(self.plot, self._open_fs)
        outer.addWidget(self.plot)

        # ── fit controls ──────────────────────────────────────────────────────

        fit_row = QHBoxLayout()
        self._fit_combo = QComboBox()
        for name in _FIT_MODELS:
            self._fit_combo.addItem(name)
        self._fit_combo.setFixedWidth(260)
        fit_row.addWidget(QLabel("Fit:"))
        fit_row.addWidget(self._fit_combo)

        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText(
            "Custom: e.g.  a * np.exp(-b * x)   (params: a, b, c)")
        self._custom_edit.setFixedWidth(280)
        fit_row.addWidget(self._custom_edit)

        self._fit_btn = QPushButton("Fit")
        self._fit_btn.setEnabled(False)
        self._fit_btn.setToolTip(f"Available after {_MIN_EVENTS_FOR_FIT} events")
        self._fit_btn.clicked.connect(self._run_fit)
        fit_row.addWidget(self._fit_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self._clear_fit)
        fit_row.addWidget(self._clear_btn)
        fit_row.addStretch()

        self._fit_lbl = QLabel("")
        self._fit_lbl.setStyleSheet("font-size:9px;color:#F0A030;")
        fit_row.addWidget(self._fit_lbl)
        outer.addLayout(fit_row)

        # ── state ─────────────────────────────────────────────────────────────

        self._raw_adc:   list[int]    = []
        self._max_bin    = 0
        self._bin_width  = _DEFAULT_BIN_WIDTH
        self._bin_count  = 0
        self._counts:    np.ndarray   = np.array([], dtype=np.int64)
        self._centers:   np.ndarray   = np.array([])
        self._fit_xy:    tuple        = ([], [])   # stored across rebuilds

        self._fs_win: _FullScreenWindow | None = None

        self._rebuild()

    # ── public ────────────────────────────────────────────────────────────────

    def add_event(self, event):
        self._raw_adc.append(event.adc)

        idx = int((event.adc - ADC_MIN) / self._bin_width)
        if 0 <= idx < self._bin_count:
            self._counts[idx] += 1
            if idx > self._max_bin:
                self._max_bin = idx
                x_max = ADC_MIN + (self._max_bin + 6) * self._bin_width
                self.plot.setXRange(ADC_MIN, min(x_max, ADC_MAX), padding=0)

        if self._bars is not None:
            self._bars.setOpts(height=self._display_heights())

        # keep log-scale tick labels in sync with growing counts
        if self._log_mode:
            self._update_log_ticks()

        if len(self._raw_adc) >= _MIN_EVENTS_FOR_FIT:
            self._fit_btn.setEnabled(True)

    def set_threshold(self, value: int):
        self.threshold_line.setValue(value)

    def reset(self):
        self._raw_adc  = []
        self._max_bin  = 0
        self._counts[:] = 0
        if self._bars is not None:
            self._bars.setOpts(height=self._display_heights())
        self._clear_fit()
        self._fit_btn.setEnabled(False)
        self.plot.setXRange(ADC_MIN, ADC_MAX, padding=0)
        self._update_log_ticks()

    # ── log scale ─────────────────────────────────────────────────────────────

    def _on_log_toggled(self, checked: bool):
        self._log_mode = checked
        self.plot.setLabel("left", "log₁₀(Counts)" if checked else "Counts")
        self.plot.setLimits(yMin=0)
        if self._bars is not None:
            self._bars.setOpts(height=self._display_heights())

        # Re-transform the fit curve if one is currently displayed.
        # _fit_xy always stores the curve in *linear* count space so we can
        # switch modes without losing the original fit.
        if self._fit_curve is not None and self._fit_xy[0]:
            x_fit = np.array(self._fit_xy[0])
            y_fit = np.array(self._fit_xy[1])   # linear counts
            if checked:
                y_display = np.log10(np.maximum(y_fit, 1e-9))
            else:
                y_display = y_fit
            self._fit_curve.setData(x_fit, y_display)

        self._update_log_ticks()

    def _display_heights(self) -> np.ndarray:
        """Bar heights for the current scale mode.

        Linear mode: raw integer counts.

        Log mode: log10(count + 0.5) for bins with ≥ 1 count.
          • count = 0 → 0.0  (bar sits at baseline, visually absent)
          • count = 1 → log10(1.5) ≈ 0.18  (small but clearly visible)
          • count = 10 → log10(10.5) ≈ 1.02
          • count = 100 → log10(100.5) ≈ 2.00
        The +0.5 offset is negligible for large counts and essential for
        distinguishing "one event" from "no events" at a glance.
        """
        if not self._log_mode:
            return self._counts.astype(float)

        out = np.zeros(len(self._counts), dtype=float)
        mask = self._counts >= 1
        out[mask] = np.log10(self._counts[mask].astype(float) + 0.5)
        return out

    def _update_log_ticks(self):
        """Set y-axis labels to show actual integer counts (1, 10, 100 …)
        at their log10 positions (0, 1, 2 …).  Called on toggle and after
        every new event while in log mode so the axis grows with the data.
        """
        axis = self.plot.getAxis("left")
        if not self._log_mode or len(self._counts) == 0:
            axis.setTicks(None)
            return

        max_count = max(int(self._counts.max()), 1)
        max_log   = np.log10(max_count + 0.5)

        # Major ticks at every power of 10
        major = []
        p = 0
        while p <= max_log + 1:
            # Position in log10(count+0.5) space for this count value
            major.append((np.log10(10**p + 0.5), str(int(10**p))))
            p += 1

        # Minor ticks at 2×, 3×, 5× each decade
        minor = []
        for decade in range(int(max_log) + 1):
            base = 10 ** decade
            for mult in (2, 3, 5):
                c = base * mult
                if c <= max_count:
                    minor.append((np.log10(c + 0.5), str(c)))

        axis.setTicks([major, minor])

    # ── bin rebuild ───────────────────────────────────────────────────────────

    def _rebuild(self):
        """Rebin from raw ADC values and re-add items in correct z-order:
           bars → fit curve → threshold line.
           (pyqtgraph renders last-added items on top)
        """

        # preserve fit data across rebuilds
        fit_x, fit_y = list(self._fit_xy[0]), list(self._fit_xy[1])

        self.plot.clear()

        bw = self._bin_spin.value()
        self._bin_width = bw
        n = max(1, (ADC_MAX - ADC_MIN) // bw + 1)
        self._bin_count = n

        edges          = np.arange(ADC_MIN, ADC_MIN + (n + 1) * bw, bw, dtype=float)
        self._centers  = (edges[:-1] + edges[1:]) / 2.0

        if self._raw_adc:
            self._counts, _ = np.histogram(self._raw_adc, bins=edges)
        else:
            self._counts = np.zeros(n, dtype=np.int64)

        # z-order 1 — bars (bottom)
        self._bars = pg.BarGraphItem(
            x=self._centers,
            height=self._display_heights(),
            width=bw,
            brush="#2f2f2f",
        )
        self.plot.addItem(self._bars)

        # z-order 2 — fit curve (above bars)
        self._fit_curve = self.plot.plot(
            pen=pg.mkPen("#F0A030", width=2,
                         style=pg.QtCore.Qt.PenStyle.DashLine))
        if fit_x:
            self._fit_curve.setData(fit_x, fit_y)
            self._fit_xy = (fit_x, fit_y)

        # z-order 3 — threshold line (topmost)
        self.plot.addItem(self.threshold_line)

        # restore x-range
        nz = np.nonzero(self._counts)[0]
        if len(nz):
            self._max_bin = int(nz[-1])
            x_max = ADC_MIN + (self._max_bin + 6) * bw
            self.plot.setXRange(ADC_MIN, min(x_max, ADC_MAX), padding=0)

        self._update_log_ticks()

    # ── fitting ───────────────────────────────────────────────────────────────

    def _run_fit(self):
        from scipy.optimize import curve_fit

        mask   = self._counts > 0
        x_data = self._centers[mask]
        y_data = self._counts[mask].astype(float)

        custom = self._custom_edit.text().strip()
        if custom:
            func, pnames = self._parse_custom(custom)
        else:
            func, pnames = _FIT_MODELS[self._fit_combo.currentText()]

        if func is None:
            self._fit_lbl.setText("Syntax error in custom equation.")
            return

        try:
            p0   = [max(y_data)] + [0.01] * (len(pnames) - 1)
            popt, pcov = curve_fit(func, x_data, y_data, p0=p0,
                                   maxfev=10_000, bounds=(0, np.inf))
            perr = np.sqrt(np.diag(pcov))

            x_fit = np.linspace(x_data[0], x_data[-1], 500)
            y_fit = func(x_fit, *popt)   # always linear counts

            # _fit_xy stores the linear-space curve so _on_log_toggled can
            # re-transform without losing the original fit
            self._fit_xy = (list(x_fit), list(y_fit))

            # display: transform to log space if currently in log mode
            y_display = np.log10(np.maximum(y_fit, 1e-9)) if self._log_mode else y_fit

            if self._fit_curve is not None:
                self._fit_curve.setData(x_fit, y_display)

            parts = [f"{n}={v:.3g}±{e:.2g}" for n, v, e in zip(pnames, popt, perr)]
            self._fit_lbl.setText("  ".join(parts))
            self._clear_btn.setEnabled(True)

        except Exception as exc:
            self._fit_lbl.setText(f"Fit failed: {exc}")

    @staticmethod
    def _parse_custom(eq: str):
        import re
        tokens = re.findall(r'\b([a-wyz])\b', eq)
        params = sorted(set(tokens))
        safe   = {"np": np, "exp": np.exp, "log": np.log,
                  "sqrt": np.sqrt, "sin": np.sin, "cos": np.cos,
                  "pi": np.pi, "e": np.e}
        try:
            compile(eq, "<custom>", "eval")
        except SyntaxError:
            return None, []

        def fn(x, *args):
            ns = dict(safe, x=x, **dict(zip(params, args)))
            return eval(eq, {"__builtins__": {}}, ns)

        return fn, params

    def _clear_fit(self):
        if self._fit_curve is not None:
            self._fit_curve.setData([], [])
        self._fit_xy = ([], [])
        self._fit_lbl.setText("")
        self._clear_btn.setEnabled(False)

    # ── fullscreen ────────────────────────────────────────────────────────────

    def _open_fs(self):
        if self._fs_win and not self._fs_win.isHidden():
            self._fs_win.activateWindow()
            return

        win = _FullScreenWindow("ADC spectrum", "Counts", time_axis=False)
        win.plot.setLimits(xMin=ADC_MIN, xMax=ADC_MAX, yMin=0)
        win.plot.getViewBox().setMouseMode(pg.ViewBox.PanMode)

        # Create bar item in the fullscreen plot
        bw = self._bin_width

        fs_bars = pg.BarGraphItem(
            x=list(self._centers),height=self._display_heights(),
            width=bw,brush="#2f2f2f",)
        win.plot.addItem(fs_bars)

        # Update bars on each timer refresh
        def _data_fn():
            fs_bars.setOpts(height=self._display_heights())
            return {}   # no line items to update

        win.register(_data_fn)
        self._fs_win = win
        win.show()


# ═══════════════════════════════════════════════════════════════════════════════
# DualRatePanel  (Coincidence tab)
# ═══════════════════════════════════════════════════════════════════════════════

_DUAL_COLORS = {
    "master":      ("#00CC55", (0, 204,  85, 160)),
    "slave":       ("#DD3333", (221,  51,  51, 160)),
    "coincidence": ("#FFCC00", (255, 204,   0, 160)),
}


class DualRatePanel(QWidget):
    """Master, slave, and coincidence rates on two shared-axis plots.

    Top    — instantaneous rate (30 s window)
    Bottom — cumulative rate with faint 1/√N bands
    Both x-axes linked.
    """

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        self.setLayout(layout)

        self._instant_window = INSTANT_WINDOW_S   # adjustable at runtime
        self._instant_label_widget = None  # will store the label for updates

        # ── legend row (above plots) ──────────────────────────────────────────
        legend_row = QHBoxLayout()
        for key, (color, _) in _DUAL_COLORS.items():
            dot = QLabel(f"● {key.capitalize()}")
            dot.setStyleSheet(f"color:{color};font-size:10px;font-weight:bold;")
            legend_row.addWidget(dot)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        # ── instantaneous plot ────────────────────────────────────────────────
        ih = QHBoxLayout()
        self._instant_label_widget = QLabel(f"Instantaneous rate — all detectors (last {self._instant_window} s)")
        ih.addWidget(self._instant_label_widget)
        ih.addStretch()
        layout.addLayout(ih)

        self.inst_plot = _base_plot()
        # Proper pyqtgraph legend anchored to top-right of the plot
        self._inst_legend = self.inst_plot.addLegend(offset=(-10, 10))
        _fs_button(self.inst_plot, self._open_inst_fs)
        layout.addWidget(self.inst_plot)

        # ── cumulative plot ───────────────────────────────────────────────────
        ch = QHBoxLayout()
        ch.addWidget(QLabel("Cumulative rate — all detectors"))
        ch.addStretch()
        reset_btn = QPushButton("Reset view")
        reset_btn.setFixedWidth(82)
        reset_btn.clicked.connect(self._reset_view)
        ch.addWidget(reset_btn)
        layout.addLayout(ch)

        self.cum_plot = _base_plot()
        self.cum_plot.setXLink(self.inst_plot)
        self._cum_legend = self.cum_plot.addLegend(offset=(-10, 10))
        _fs_button(self.cum_plot, self._open_cum_fs)
        layout.addWidget(self.cum_plot)

        # ── per-source items ──────────────────────────────────────────────────
        self._src: dict[str, dict] = {}

        for key, (line_color, pt_rgba) in _DUAL_COLORS.items():
            pen   = pg.mkPen(line_color, width=2)
            faint = pg.mkBrush(*pt_rgba[:3], 30)

            ic = self.inst_plot.plot(pen=pen, name=key)

            cu = self.cum_plot.plot(pen=pg.mkPen(line_color, width=1, alpha=80))
            cl = self.cum_plot.plot(pen=pg.mkPen(line_color, width=1, alpha=80))
            self.cum_plot.addItem(pg.FillBetweenItem(cu, cl, brush=faint))
            cc = self.cum_plot.plot(pen=pen)

            self._src[key] = dict(
                ev_times=deque(), total=0,
                times=[0.0], inst=[0.0], cum=[0.0], upper=[0.0], lower=[0.0],
                ic=ic, cc=cc, cu=cu, cl=cl,
            )

        self._start  = time.monotonic()
        self._last_t = 0.0
        self._fs_inst: _FullScreenWindow | None = None
        self._fs_cum:  _FullScreenWindow | None = None

    # ── public ────────────────────────────────────────────────────────────────

    def set_instant_window(self, seconds: int):
        """Change the sliding window used for the instantaneous rate curve."""
        self._instant_window = max(1, seconds)
        if self._instant_label_widget:
            self._instant_label_widget.setText(
                f"Instantaneous rate — all detectors (last {self._instant_window} s)"
            )

    def add_master_event(self, event):      self._record("master")
    def add_slave_event(self, event):       self._record("slave")
    def add_coincidence_event(self):        self._record("coincidence")

    def tick(self):
        now = time.monotonic()
        if now - self._last_t < RATE_TICK_S:
            return
        self._last_t = now

        elapsed  = now - self._start
        cut_hist = elapsed - MAX_HISTORY_S

        for key, s in self._src.items():
            cut = now - INSTANT_WINDOW_S
            while s["ev_times"] and s["ev_times"][0] < cut:
                s["ev_times"].popleft()

            inst  = len(s["ev_times"]) / INSTANT_WINDOW_S
            cum   = s["total"] / max(elapsed, 1e-6)
            lower_ci, cum_mean, upper_ci = _bayesian_rate_interval(
                N=s["total"],
                t=max(elapsed, 1e-6),
                prior_rate=0.5,
                conf=0.95
            )

            s["times"].append(elapsed)
            s["inst"].append(inst)
            s["cum"].append(cum_mean)
            s["upper"].append(upper_ci)
            s["lower"].append(lower_ci)

            while s["times"] and s["times"][0] < cut_hist:
                for k in ("times","inst","cum","upper","lower"):
                    s[k].pop(0)

            t = s["times"]
            s["ic"].setData(t, s["inst"])
            s["cc"].setData(t, s["cum"])
            s["cu"].setData(t, s["upper"])
            s["cl"].setData(t, s["lower"])
            
            window_n = max(1, int(self._instant_window / RATE_TICK_S))
            recent = s["inst"][-window_n:] if len(s["inst"]) > 0 else []

            if recent:
                s["mean"] = float(np.mean(recent))
                s["median"] = float(np.median(recent))
                s["std"] = float(np.std(recent))

    def reset(self):
        self._start  = time.monotonic()
        self._last_t = 0.0
        for s in self._src.values():
            s["ev_times"].clear();  s["total"] = 0
            for k in ("times","inst","cum","upper","lower"):
                s[k] = [0.0]
            s["ic"].setData([0.0],[0.0])
            s["cc"].setData([0.0],[0.0])
            s["cu"].setData([0.0],[0.0])
            s["cl"].setData([0.0],[0.0])

    # ── internal ──────────────────────────────────────────────────────────────

    def _record(self, key: str):
        s = self._src[key]
        s["ev_times"].append(time.monotonic())
        s["total"] += 1

    def _reset_view(self):
        self.inst_plot.enableAutoRange()
        self.cum_plot.enableAutoRange()

    def _open_inst_fs(self):
        if self._fs_inst and not self._fs_inst.isHidden():
            self._fs_inst.activateWindow(); return
        win = _FullScreenWindow("Instantaneous rates (all detectors)", "Rate [Hz]")
        for key, (color, _) in _DUAL_COLORS.items():
            win.add_line(f"line_{key}", pg.mkPen(color, width=2))
        win.register(lambda: {
            f"line_{k}": (s["times"], s["inst"])
            for k, s in self._src.items()
        })
        self._fs_inst = win; win.show()

    def _open_cum_fs(self):
        if self._fs_cum and not self._fs_cum.isHidden():
            self._fs_cum.activateWindow(); return
        win = _FullScreenWindow("Cumulative rates (all detectors)", "Rate [Hz]")
        for key, (color, rgba) in _DUAL_COLORS.items():
            win.add_fill(f"fill_{key}", f"u_{key}", f"l_{key}", (*rgba[:3], 30))
            win.add_line(f"line_{key}", pg.mkPen(color, width=2))
        win.register(lambda: {
            **{f"u_{k}":    (s["times"], s["upper"]) for k, s in self._src.items()},
            **{f"l_{k}":    (s["times"], s["lower"]) for k, s in self._src.items()},
            **{f"line_{k}": (s["times"], s["cum"])   for k, s in self._src.items()},
        })
        self._fs_cum = win; win.show()
