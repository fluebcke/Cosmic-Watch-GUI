# -----------------
# Commands sent TO the Pico
# -----------------

CMD_RESET = "RESET"
CMD_START = "START"
CMD_REBOOT = "REBOOT"
CMD_PING = "PING"

CMD_THRESHOLD_PREFIX = "THRESHOLD:"
CMD_NAME_PREFIX = "NAME:"


def cmd_threshold(value: int) -> str:
    return f"{CMD_THRESHOLD_PREFIX}{value}"


def cmd_name(name: str) -> str:
    return f"{CMD_NAME_PREFIX}{name}"


# -----------------
# Responses received FROM the Pico
# -----------------

RESP_MEASUREMENT_RESET_OK = "MEASUREMENT_RESET_OK"
RESP_MEASUREMENT_START_OK = "MEASUREMENT_START_OK"
RESP_PONG = "PONG"
RESP_REBOOTING = "REBOOTING"

RESP_THRESHOLD_OK_PREFIX = "THRESHOLD_OK:"
RESP_THRESHOLD_ERR_PREFIX = "THRESHOLD_ERR:"

RESP_NAME_OK_PREFIX = "NAME_OK:"
RESP_NAME_ERR_PREFIX = "NAME_ERR:"

RESP_ROLE_PREFIX = "Role:"
RESP_READY = "READY"

EVENT_HEADER = "evNum\tpicoTimeMs\tadcAtEvent\trateOverall\tThreshold"


# -----------------
# Internal status tags
# -----------------
# Not sent by the Pico — generated locally by DetectorReader to
# signal connection-level events through the responses queue.

TAG_CONNECTION_LOST = "CONNECTION_LOST:"


# -----------------
# Limits
# -----------------
# Must match THRESHOLD_MIN / THRESHOLD_MAX in the firmware (.ino) exactly.

THRESHOLD_MIN = 20
THRESHOLD_MAX = 1000

NAME_MAX_LENGTH = 17
