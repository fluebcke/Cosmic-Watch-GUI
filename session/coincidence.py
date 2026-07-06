"""
CoincidenceSession — two-detector event matching.

Matching strategy
-----------------
Each Pico has its own independent millisecond timer that starts at 0 on reset,
so pico_time_ms cannot be used to correlate events across two detectors.
Instead, every MuonEvent is stamped with pc_time_s (time.monotonic()) in the
reader thread the moment the line is received.  Serial latency is typically
1–5 ms and nearly identical for two USB devices on the same host, so
pc_time_s provides a shared reference good to ~5–10 ms.

COINC_WINDOW_S is set to 20 ms — wide enough to absorb serial jitter,
narrow enough that the accidental coincidence rate (λ_M × λ_S × 2W) is
negligible at typical muon rates (~1 Hz each gives ~0.04 accidentals/hour).

Three event categories are returned by process():
  - master_only   : master events with no slave partner
  - slave_only    : slave events with no master partner
  - coincidences  : matched pairs as CoincidenceEvent objects

Anti-coincidence (master_only) is the natural by-product of the matching
loop and requires no additional logic.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from detector.parser import MuonEvent
from detector.detector import DetectorReader


COINC_WINDOW_S = 0.020   # 20 ms software matching window
MAX_PENDING    = 500      # safety cap on unmatched event buffers


@dataclass
class CoincidenceEvent:
    """A hardware-coincident pair: one event from each detector."""
    master:     MuonEvent
    slave:      MuonEvent
    delta_t_ms: float       # slave.pc_time_s - master.pc_time_s, in ms


class CoincidenceSession:
    """
    Wraps two DetectorReader instances and matches their events by PC timestamp.

    Call process() on every GUI timer tick to drain both queues and receive
    categorised event lists.
    """

    def __init__(self, master: DetectorReader, slave: DetectorReader):

        self.master = master
        self.slave  = slave

        # unmatched events waiting for a partner
        self._pending_master: deque[MuonEvent] = deque(maxlen=MAX_PENDING)
        self._pending_slave:  deque[MuonEvent] = deque(maxlen=MAX_PENDING)

        # running totals
        self.n_master       = 0
        self.n_slave        = 0
        self.n_coincidences = 0
        self.n_anti         = 0   # master events confirmed solo (anti-coincidence)


    def start(self):

        self.master.start()
        self.slave.start()

        self.master.start_measurement()
        self.slave.start_measurement()


    def stop(self):

        self.master.stop()
        self.slave.stop()


    def process(self) -> tuple[
        list[MuonEvent],
        list[MuonEvent],
        list[CoincidenceEvent],
    ]:
        """
        Drain both queues, attempt timestamp matching, and return:
          master_events  — all new master events (matched + unmatched)
          slave_events   — all new slave events  (matched + unmatched)
          coincidences   — matched CoincidenceEvent pairs found this tick

        Events remain in the pending buffers until either matched or
        confirmed as too old (older than COINC_WINDOW_S × 10 to allow
        for high rate bursts without immediately expiring everything).
        """

        import time
        now = time.monotonic()

        # ── drain queues into local lists ─────────────────────────────────────
        master_new: list[MuonEvent] = []
        slave_new:  list[MuonEvent] = []

        while not self.master.queue.empty():
            ev = self.master.queue.get()
            master_new.append(ev)
            self._pending_master.append(ev)
            self.n_master += 1

        while not self.slave.queue.empty():
            ev = self.slave.queue.get()
            slave_new.append(ev)
            self._pending_slave.append(ev)
            self.n_slave += 1

        # ── timestamp matching ────────────────────────────────────────────────
        coincidences: list[CoincidenceEvent] = []

        matched_m: set[int] = set()
        matched_s: set[int] = set()

        pending_m = list(self._pending_master)
        pending_s = list(self._pending_slave)

        for i, m in enumerate(pending_m):
            if i in matched_m:
                continue
            for j, s in enumerate(pending_s):
                if j in matched_s:
                    continue
                dt = s.pc_time_s - m.pc_time_s
                if abs(dt) <= COINC_WINDOW_S:
                    coincidences.append(
                        CoincidenceEvent(
                            master=m,
                            slave=s,
                            delta_t_ms=dt * 1000.0,
                        )
                    )
                    matched_m.add(i)
                    matched_s.add(j)
                    self.n_coincidences += 1
                    break

        # ── expire old unmatched events ───────────────────────────────────────
        # Events older than 10× the coincidence window are guaranteed
        # unmatched — remove them and count as anti-coincidences (master)
        # or singles (slave).
        expire_cutoff = now - COINC_WINDOW_S * 10

        expired_m = {
            i for i, ev in enumerate(pending_m)
            if ev.pc_time_s < expire_cutoff and i not in matched_m
        }
        self.n_anti += len(expired_m)
        matched_m |= expired_m

        expired_s = {
            j for j, ev in enumerate(pending_s)
            if ev.pc_time_s < expire_cutoff and j not in matched_s
        }
        matched_s |= expired_s

        # rebuild pending buffers without matched/expired entries
        self._pending_master = deque(
            [ev for i, ev in enumerate(pending_m) if i not in matched_m],
            maxlen=MAX_PENDING,
        )
        self._pending_slave = deque(
            [ev for j, ev in enumerate(pending_s) if j not in matched_s],
            maxlen=MAX_PENDING,
        )

        return master_new, slave_new, coincidences

    # ── convenience properties ────────────────────────────────────────────────

    @property
    def coincidence_fraction(self) -> float:
        """Coincidences / master singles — detector geometric acceptance proxy."""
        if self.n_master == 0:
            return 0.0
        return self.n_coincidences / self.n_master
