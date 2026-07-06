from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QHBoxLayout, QSpinBox, QFileDialog, QLabel, QGroupBox,
)


# Default window sizes in seconds offered to the user.
# Each value produces one rate tile in LiveStatsBar.
DEFAULT_WINDOWS = [30, 60, 300]


class SettingsDialog(QDialog):
    """Configuration options not needed constantly during a session.

    - Author name  (sent to detector via NAME: command)
    - Log directory
    - Rate counter windows: the user can set 1–4 custom time windows
      (in seconds) that are displayed as rate tiles in LiveStatsBar.
      Changes take effect immediately when the dialog is accepted.
    """

    def __init__(self, parent, current_name="", current_log_dir="measurements",
                 current_windows=None, current_live_rate=5):

        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)

        layout = QVBoxLayout()
        self.setLayout(layout)

        form = QFormLayout()
        layout.addLayout(form)

        # ── author name ───────────────────────────────────────────────────────
        self.name_edit = QLineEdit(current_name)
        self.name_edit.setMaxLength(17)
        self.name_edit.setPlaceholderText("max 17 characters")
        form.addRow("Author name:", self.name_edit)

        # ── log directory ─────────────────────────────────────────────────────
        log_row = QHBoxLayout()
        self.log_dir_edit = QLineEdit(current_log_dir)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_log_dir)
        log_row.addWidget(self.log_dir_edit)
        log_row.addWidget(browse_btn)
        form.addRow("Log directory:", log_row)

        # ── live rate window ────────────────────────────────────────────────────
        live_rate_row = QHBoxLayout()
        live_rate_row.addWidget(QLabel("Live rate window:"))
        self.live_rate_spin = QSpinBox()
        self.live_rate_spin.setRange(1, 60)
        self.live_rate_spin.setValue(int(current_live_rate))
        self.live_rate_spin.setSuffix(" s")
        self.live_rate_spin.setToolTip("Sliding window for instantaneous rate (RatePanel and DualRatePanel)")
        self.live_rate_spin.setFixedWidth(80)
        live_rate_row.addWidget(self.live_rate_spin)
        live_rate_row.addStretch()
        form.addRow("", live_rate_row)

        # ── rate counter windows ──────────────────────────────────────────────
        windows_box = QGroupBox("Rate counter windows (LiveStatsBar)")
        windows_layout = QVBoxLayout()
        windows_box.setLayout(windows_layout)

        windows_layout.addWidget(
            QLabel("Each window produces one rate tile in the stats bar.\n"
                   "Enter time in seconds (e.g. 30 = last 30 s rate).")
        )

        windows = list(current_windows or DEFAULT_WINDOWS)

        spin_row = QHBoxLayout()
        self.window_spins: list[QSpinBox] = []

        for w in windows:
            col = QVBoxLayout()

            spin = QSpinBox()
            spin.setRange(5, 86400)
            spin.setValue(int(w))
            spin.setSuffix(" s")
            spin.setFixedWidth(90)
            self.window_spins.append(spin)

            caption = QLabel(self._label_for(int(w)))
            caption.setStyleSheet("font-size: 9px; color: #888;")
            spin.valueChanged.connect(
                lambda v, lbl=caption: lbl.setText(self._label_for(v))
            )

            col.addWidget(spin)
            col.addWidget(caption)
            spin_row.addLayout(col)

        spin_row.addStretch()
        windows_layout.addLayout(spin_row)
        layout.addWidget(windows_box)

        # ── buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        save_btn   = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)


    # ── helpers ───────────────────────────────────────────────────────────────

    def _browse_log_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choose log directory", self.log_dir_edit.text()
        )
        if path:
            self.log_dir_edit.setText(path)

    @staticmethod
    def _label_for(seconds: int) -> str:
        """Human-readable label shown under each window spinbox."""
        if seconds < 120:
            return f"last {seconds} s"
        if seconds < 7200:
            return f"last {seconds // 60} min"
        return f"last {seconds // 3600} h"

    def values(self) -> dict:
        """Call after exec() returns Accepted."""
        return {
            "name":              self.name_edit.text().strip(),
            "log_dir":           self.log_dir_edit.text().strip() or "measurements",
            "rate_windows":      [s.value() for s in self.window_spins],
            "live_rate_window":  self.live_rate_spin.value(),
        }
