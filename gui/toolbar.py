from PyQt6.QtWidgets import (
    QToolBar,
    QComboBox,
    QPushButton,
    QLabel,
    QSlider,
    QSpinBox,
    QLineEdit,
)

from PyQt6.QtCore import Qt, pyqtSignal
import serial
from serial.tools import list_ports

from detector import protocol


def _is_port_available(port: str, timeout: float = 0.3) -> bool:
    """Quick check if a port is actually connected to a device."""
    try:
        ser = serial.Serial(port, 115200, timeout=timeout)
        ser.close()
        return True
    except (serial.SerialException, OSError, FileNotFoundError):
        return False


class Toolbar(QToolBar):

    # Signals emitted upward to MainWindow
    connect_clicked = pyqtSignal(str)      # port
    disconnect_clicked = pyqtSignal()
    threshold_changed = pyqtSignal(int)
    name_changed = pyqtSignal(str)
    logging_toggled = pyqtSignal(bool)     # True = start logging, False = stop
    restart_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()

    def __init__(self, hide_connect: bool = False):

        super().__init__("Controls")

        self.setMovable(False)

        self.connected = False
        self.logging_active = False
        self._hide_connect = hide_connect

        self._build()


    def _build(self):

        # -----------------
        # Port selection + Connect — hidden in coincidence mode since both
        # detectors are connected before MainWindow is created.
        # -----------------

        if not self._hide_connect:

            self.addWidget(QLabel("  Port: "))

            self.port_combo = QComboBox()
            self.port_combo.setMinimumWidth(160)
            self._refresh_ports()
            self.addWidget(self.port_combo)

            refresh_btn = QPushButton("Refresh")
            refresh_btn.clicked.connect(self._refresh_ports)
            self.addWidget(refresh_btn)

            self.addSeparator()

            self.connect_btn = QPushButton("Connect")
            self.connect_btn.clicked.connect(self._on_connect_clicked)
            self.addWidget(self.connect_btn)

        else:
            # create a stub so set_connected() doesn't crash when it
            # tries to update the button text
            self.connect_btn = QPushButton()
            self.connect_btn.hide()


        # -----------------
        # Restart measurement
        # -----------------

        self.restart_btn = QPushButton("Restart")
        self.restart_btn.setToolTip("Reset the detector's counters and begin a fresh measurement")
        self.restart_btn.setEnabled(False)
        self.restart_btn.clicked.connect(self.restart_clicked.emit)

        self.addWidget(self.restart_btn)


        self.addSeparator()


        # -----------------
        # Threshold — slider + exact spinbox, kept in sync
        # -----------------

        self.addWidget(QLabel("  Threshold: "))

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setMinimum(protocol.THRESHOLD_MIN)
        self.threshold_slider.setMaximum(protocol.THRESHOLD_MAX)
        self.threshold_slider.setValue(150)
        self.threshold_slider.setFixedWidth(140)
        self.threshold_slider.setEnabled(False)

        self.addWidget(self.threshold_slider)


        self.threshold_spin = QSpinBox()
        self.threshold_spin.setMinimum(protocol.THRESHOLD_MIN)
        self.threshold_spin.setMaximum(protocol.THRESHOLD_MAX)
        self.threshold_spin.setValue(150)
        self.threshold_spin.setSuffix(" mV")
        self.threshold_spin.setFixedWidth(90)
        self.threshold_spin.setEnabled(False)

        self.addWidget(self.threshold_spin)

        self.threshold_slider.valueChanged.connect(self.threshold_spin.setValue)
        self.threshold_spin.valueChanged.connect(self.threshold_slider.setValue)

        self.threshold_slider.sliderReleased.connect(self._on_threshold_commit)
        self.threshold_spin.editingFinished.connect(self._on_threshold_commit)


        self.addSeparator()


        # -----------------
        # Start / Stop logging
        # -----------------

        self.logging_btn = QPushButton("Start Logging")
        self.logging_btn.setEnabled(False)
        self.logging_btn.clicked.connect(self._on_logging_clicked)

        self.addWidget(self.logging_btn)


        self.addSeparator()


        # -----------------
        # Settings
        # -----------------

        settings_btn = QPushButton("⚙ Settings")
        settings_btn.clicked.connect(self.settings_clicked.emit)

        self.addWidget(settings_btn)


    # -----------------
    # Public API
    # -----------------

    def set_connected(self, connected: bool):

        self.connected = connected

        self.connect_btn.setText("Disconnect" if connected else "Connect")

        if hasattr(self, "port_combo"):
            self.port_combo.setEnabled(not connected)

        self.restart_btn.setEnabled(connected)
        self.threshold_slider.setEnabled(connected)
        self.threshold_spin.setEnabled(connected)
        #self.name_edit.setEnabled(connected)
        #self.name_btn.setEnabled(connected)
        self.logging_btn.setEnabled(connected)

        if not connected:
            self.set_logging_active(False)

    def set_logging_active(self, active: bool):

        self.logging_active = active
        self.logging_btn.setText("Stop Logging" if active else "Start Logging")

    def set_threshold_value(self, value: int):
        """Update the displayed threshold without emitting threshold_changed
        (e.g. when syncing from a STATUS response rather than user input)."""

        self.threshold_slider.blockSignals(True)
        self.threshold_spin.blockSignals(True)

        self.threshold_slider.setValue(value)
        self.threshold_spin.setValue(value)

        self.threshold_slider.blockSignals(False)
        self.threshold_spin.blockSignals(False)

    def current_port(self) -> str:

        if hasattr(self, "port_combo"):
            return self.port_combo.currentText()
        return ""

    def set_coincidence_mode(self, enabled: bool):
        """Disable measurement controls in coincidence mode (already pre-configured).
        Settings button remains enabled."""
        if enabled:
            # Disable controls that shouldn't be changed mid-measurement
            self.restart_btn.setEnabled(False)
            self.threshold_slider.setEnabled(False)
            self.threshold_spin.setEnabled(False)
            self.logging_btn.setEnabled(False)
        else:
            # Re-enable if switching back (unlikely)
            self.restart_btn.setEnabled(self.connected)
            self.threshold_slider.setEnabled(self.connected)
            self.threshold_spin.setEnabled(self.connected)
            self.logging_btn.setEnabled(self.connected)


    # -----------------
    # Internal slots
    # -----------------

    def _refresh_ports(self):

        current = self.port_combo.currentText()

        self.port_combo.clear()

        ports = list(list_ports.comports())
        ports.sort(key=lambda p: p.device)

        for p in ports:
            is_available = _is_port_available(p.device)
            self.port_combo.addItem(p.device)
            # Grey out if not available
            if not is_available:
                self.port_combo.model().item(self.port_combo.count() - 1).setEnabled(False)

        idx = self.port_combo.findText(current)

        if idx >= 0:
            self.port_combo.setCurrentIndex(idx)

    def _on_connect_clicked(self):

        if self.connected:
            self.disconnect_clicked.emit()
        else:
            port = self.current_port()

            if port:
                self.connect_clicked.emit(port)

    def _on_threshold_commit(self):

        self.threshold_changed.emit(self.threshold_slider.value())



    def _on_logging_clicked(self):

        # toggle and let MainWindow decide whether the start actually
        # succeeds (e.g. file system error) — it calls set_logging_active()
        # back once it knows the real outcome.
        self.logging_toggled.emit(not self.logging_active)
