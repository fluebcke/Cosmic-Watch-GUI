from dataclasses import dataclass, field


@dataclass
class MuonEvent:
    evNum:     int
    time_ms:   int
    adc:       int
    rate:      float
    threshold: int
    # PC-side monotonic timestamp (seconds) added by DetectorReader when the
    # line is received.  This is the only reliable shared time reference for
    # software coincidence matching between two independent Picos, since both
    # Picos start their own pico_time_ms counter at 0 on every reset.
    pc_time_s: float = field(default=0.0)


def parse_event(line: str) -> MuonEvent | None:

    parts = line.strip().split("\t")

    if len(parts) != 5:
        return None

    try:
        return MuonEvent(
            evNum     = int(parts[0]),
            time_ms   = int(parts[1]),
            adc       = int(parts[2]),
            rate      = float(parts[3]),
            threshold = int(parts[4]),
            # pc_time_s is set to 0.0 here; DetectorReader overwrites it
            # immediately after parse_event() returns.
        )

    except ValueError:
        return None
