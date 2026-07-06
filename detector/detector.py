from __future__ import annotations

import queue
import time
import threading
import serial

from .parser import parse_event
from . import protocol


class DetectorReader:

    def __init__(self, port: str | None = None, baud: int = 115200):
        self.port = port
        self.baud = baud
        self.ser = None
        self.running = False
        self.thread = None
        self.queue = queue.Queue()
        self.responses = queue.Queue()
        self.connected = False
        self.last_error = ""

    def connect(self):

        self.ser = serial.Serial(self.port, self.baud, timeout=1)
        self.connected = True
        self.last_error = ""

    def disconnect(self):

        self.connected = False
        if self.ser:
            self.ser.close()
            self.ser = None

    def send_command(self, cmd: str):

        if not self.ser:
            return
        self.ser.write((cmd + "\n").encode())
        self.ser.flush()

    def read_line(self):

        raw = self.ser.readline()
        if not raw:
            return None
        return raw.decode(errors="replace").strip()

    def start(self):

        self.connect()
        self.running = True
        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.thread.start()

    def stop(self):

        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self.disconnect()

    def _reader_loop(self):

        while self.running:

            try:
                line = self.read_line()
            except serial.SerialException as e:
                self.connected = False
                self.last_error = str(e)
                self.responses.put(f"{protocol.TAG_CONNECTION_LOST}{e}")
                break

            if not line:
                continue

            event = parse_event(line)

            if event:
                # stamp with PC monotonic time immediately — this is the
                # shared reference used for software coincidence matching
                event.pc_time_s = time.monotonic()
                self.queue.put(event)
            else:
                # Suppress the firmware column header and the reset/start
                # acknowledgement lines — they are not user-facing responses
                # and would clutter the status bar permanently if shown.
                if (line.startswith("evNum")
                        or line == protocol.RESP_MEASUREMENT_RESET_OK
                        or line == protocol.RESP_MEASUREMENT_START_OK):
                    continue
                self.responses.put(line)

    # ── command helpers ───────────────────────────────────────────────────────

    def set_threshold(self, value: int):

        if not (protocol.THRESHOLD_MIN <= value <= protocol.THRESHOLD_MAX):
            self.responses.put(
                f"{protocol.RESP_THRESHOLD_ERR_PREFIX}"
                f"client_side_out_of_range:{protocol.THRESHOLD_MIN}-{protocol.THRESHOLD_MAX}"
            )
            return
        self.send_command(protocol.cmd_threshold(value))

    def set_name(self, name: str):

        if len(name) > protocol.NAME_MAX_LENGTH:
            self.responses.put(
                f"{protocol.RESP_NAME_ERR_PREFIX}"
                f"client_side_too_long_max_{protocol.NAME_MAX_LENGTH}"
            )
            return
        self.send_command(protocol.cmd_name(name))

    def reset(self):
        self.send_command(protocol.CMD_RESET)

    def start_measurement(self):
        self.send_command(protocol.CMD_START)

    def reboot(self):
        self.send_command(protocol.CMD_REBOOT)

    def ping(self):
        self.send_command(protocol.CMD_PING)
