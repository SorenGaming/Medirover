"""Serial link to the base ESP32: read its lines and send commands (format in LAES_MIG.txt)."""
import logging
import re
from threading import Condition, Lock
from uuid import UUID

from fastapi import HTTPException
from serial import Serial, SerialException

LOG = logging.getLogger("uvicorn.error").getChild("uart")
MAX_FRAME = 64
TRIP = rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
EVENT = re.compile(
    rb"(?P<kind>OK|NAK|STARTED|ACK|HOME|ERR),(?P<trip>" + TRIP + rb")"
    rb"(?:,(?P<value>[0-9A-Z_]{1,12}))?\r?\n"
)
TEMPERATURE = re.compile(
    rb"TEMP,rover,(?P<celsius>-?\d{1,3}(?:\.\d{1,2})?)"
    rb"(?:,(?P<humidity>\d{1,3}(?:\.\d{1,2})?))?\r?\n"
)


def read_frames(port, stop, accept):
    """Collect bytes into lines of at most MAX_FRAME bytes and pass each line on."""
    frame = bytearray()
    discard = False
    while not stop.is_set():
        byte = port.read()
        if not byte:
            continue
        if not discard:
            frame.extend(byte)
        if byte == b"\n":
            if discard:
                LOG.warning("UART rejected: frame too long")
            else:
                accept(bytes(frame))
            frame.clear()
            discard = False
        elif len(frame) >= MAX_FRAME:
            frame.clear()
            discard = True


def accept_frame(frame, event, temperature_callback=None):
    """Handle one line. event(kind, trip, value) receives OK/NAK and the trip events."""
    measurement = TEMPERATURE.fullmatch(frame)
    if measurement is not None:
        value = float(measurement["celsius"])
        if temperature_callback is None or not -100 <= value <= 150:
            LOG.warning("UART rejected: temperature receiver unavailable or invalid value")
            return
        humidity = float(measurement["humidity"]) if measurement["humidity"] is not None else None
        if humidity is not None and not 0 <= humidity <= 100:
            LOG.warning("UART rejected: invalid relative humidity")
            return
        try:
            if humidity is None:
                temperature_callback(value)
            else:
                temperature_callback(value, humidity)
        except HTTPException:
            LOG.warning("UART rejected: temperature storage unavailable")
        else:
            LOG.info("UART temperature stored: %.2f C", value)
        return
    match = EVENT.fullmatch(frame)
    if match is None:
        LOG.info("UART not used: %r", frame)          # '#' text and events the server does not store
        return
    kind = match["kind"].decode("ascii")
    trip = UUID(match["trip"].decode("ascii"))
    value = match["value"].decode("ascii") if match["value"] else None
    try:
        event(kind, trip, value)
    except HTTPException as error:
        LOG.warning("UART rejected: %s trip=%s value=%s HTTP %s %s",
                    kind, trip, value, error.status_code, error.detail)
    else:
        LOG.info("UART accepted: %s trip=%s value=%s", kind, trip, value)


class Base:
    """Owns the serial port. run() reads and reopens the port; command() waits for OK/NAK."""

    def __init__(self, device, event, temperature_callback):
        self.device = device
        self.event = event
        self.temperature_callback = temperature_callback
        self.port = None
        self.sending = Lock()                     # one command at a time
        self.answered = Condition()
        self.replies = {}                         # trip -> None (OK) or the reason for NAK

    def run(self, stop):
        while not stop.is_set():
            port = Serial()
            port.port, port.baudrate, port.timeout = self.device, 115200, 0.2
            port.dtr = port.rts = False               # set before open: do not reset the ESP32
            try:
                port.open()
                self.port = port
                LOG.info("UART open: %s", self.device)
                read_frames(port, stop, self.accept)
            except SerialException as error:
                LOG.warning("UART unavailable (%s), retrying in 2 s", error)
            finally:
                self.port = None
                port.close()
            stop.wait(2)

    def accept(self, frame):
        try:
            accept_frame(frame, self.reply_or_event, self.temperature_callback)
        except Exception:                             # one bad line must not stop the reader
            LOG.exception("UART line failed: %r", frame)

    def reply_or_event(self, kind, trip, value):
        if kind in ("OK", "NAK"):
            with self.answered:
                self.replies[trip] = value
                self.answered.notify_all()
        else:
            self.event(kind, trip, value)

    def command(self, line, trip, timeout=3):
        """Send one line, e.g. ORDER,<trip>,1, and wait for the base's answer to that trip.
        Raises HTTPException unless the answer is OK."""
        with self.sending:
            port = self.port
            if port is None:
                raise HTTPException(503, "The base is not connected")
            with self.answered:
                self.replies.pop(trip, None)
            try:
                port.write(line.encode("ascii") + b"\n")
            except SerialException:
                raise HTTPException(503, "The base is not connected") from None
            with self.answered:
                if not self.answered.wait_for(lambda: trip in self.replies, timeout):
                    raise HTTPException(504, "The base did not answer")
                reason = self.replies.pop(trip)
        if reason is not None:
            raise HTTPException(409, "The base refused: " + reason)
