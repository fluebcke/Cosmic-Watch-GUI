import sys

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QRadioButton,
    QPushButton,
    QGroupBox,
)
from serial.tools import list_ports

from detector.detector import DetectorReader
from gui.main_window import MainWindow


# -----------------
# Startup dialog
# -----------------

class StartupDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Cosmic Watch — Setup")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Mode selection (ONLY informational now)
        mode_box = QGroupBox("Operation Mode")
        mode_layout = QVBoxLayout()

        self._single_radio = QRadioButton("Single Detector")
        self._single_radio.setChecked(True)

        self._coincidence_radio = QRadioButton("Coincidence Mode (Hardware linked)")

        mode_layout.addWidget(self._single_radio)
        mode_layout.addWidget(self._coincidence_radio)
        mode_box.setLayout(mode_layout)
        layout.addWidget(mode_box)

        # Port selection (ONLY ONE DEVICE)
        ports = sorted([p.device for p in list_ports.comports()])

        self._port_combo = QComboBox()
        self._port_combo.addItems(ports)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("USB Port:"))
        port_row.addWidget(self._port_combo)
        layout.addLayout(port_row)

        # Buttons
        btn_row = QHBoxLayout()

        ok_btn = QPushButton("Start")
        cancel_btn = QPushButton("Quit")

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

    def result(self):
        """Return selected detector + mode flag."""
        detector = DetectorReader(port=self._port_combo.currentText())
        is_coincidence = self._coincidence_radio.isChecked()
        return detector, is_coincidence


# -----------------
# Entry point
# -----------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Cosmic Watch")
    app.setOrganizationName("CosmicLab")

    dialog = StartupDialog()

    if dialog.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    detector, is_coincidence = dialog.result()

    window = MainWindow(detector)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
