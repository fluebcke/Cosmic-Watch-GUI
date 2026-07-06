import os
import time
from datetime import datetime


# Column header written to every log file — must match the field order in
# write_event() exactly so the file is directly importable as a TSV.
_COLUMNS = "pc_timestamp\tevNum\tpicoTimeMs\tadcAtEvent\trateOverall\tthreshold_mV"


class SessionLogger:
    """Handles start/stop logging to a file.

    Format (tab-separated, one row per event):
      pc_timestamp  evNum  picoTimeMs  adcAtEvent  rateOverall  threshold_mV

    Metadata comments at the top use '#' prefix and are ignored by pandas /
    numpy when loaded with comment='#'.
    """

    def __init__(self, base_dir: str = "measurements"):
        self.base_dir   = base_dir
        self.active     = False
        self._file      = None
        self._path      = None
        self._start_time = None

    def start(self, port: str, baud: int, threshold, author: str) -> str:
        """Create a new log file, write metadata + column header. Returns path."""

        os.makedirs(self.base_dir, exist_ok=True)

        folder          = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        measurement_dir = os.path.join(self.base_dir, folder)
        os.makedirs(measurement_dir, exist_ok=True)

        self._path = os.path.join(measurement_dir, "detector_log.txt")
        self._file = open(self._path, "a", encoding="utf-8", buffering=1)

        now = self._now_ts()

        # ── metadata block (comment lines, ignored by data parsers) ──────────
        self._file.write(f"# Detector log started : {now}\n")
        self._file.write(f"# Port                 : {port}  Baud: {baud}\n")
        self._file.write(f"# Author               : {author}\n")
        self._file.write(f"# Threshold            : {threshold} mV\n")
        self._file.write(f"# Columns              : {_COLUMNS}\n")
        self._file.write("#\n")

        # ── column header ─────────────────────────────────────────────────────
        self._file.write(_COLUMNS + "\n")

        self.active      = True
        self._start_time = time.monotonic()

        return self._path

    def stop(self):

        if self._file:
            self._file.write(f"# Detector log ended : {self._now_ts()}\n")
            self._file.close()
            self._file = None

        self.active = False

    def write_event(self, event):
        """Write one event row — columns must match _COLUMNS order exactly."""

        if not self.active or not self._file:
            return

        self._file.write(
            f"{self._now_ts()}\t"
            f"{event.evNum}\t"
            f"{event.time_ms}\t"
            f"{event.adc}\t"
            f"{event.rate:.4f}\t"
            f"{event.threshold}\n"
        )

    def elapsed(self) -> float:

        if self._start_time is None:
            return 0.0
        return time.monotonic() - self._start_time

    @property
    def path(self):
        return self._path

    @staticmethod
    def _now_ts() -> str:
        return datetime.now().isoformat(sep=" ", timespec="milliseconds")
