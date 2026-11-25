"""Read provisional station acknowledgements from a configured serial port."""
import logging
import re
from uuid import UUID

from fastapi import HTTPException
from serial import SerialException

LOG = logging.getLogger("uvicorn.error").getChild("uart")
ACK = re.compile(
    rb"ACK,(?P<trip>[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}),"
    rb"(?P<station>[12])\r?\n"
)
MAX_FRAME = 64


def read_receipts(port, stop, acknowledge):
    frame = bytearray()
    discard = False
    try:
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
                    accept_frame(frame, acknowledge)
                frame.clear()
                discard = False
            elif len(frame) >= MAX_FRAME:
                frame.clear()
                discard = True
    except SerialException:
        LOG.exception("UART reader stopped")


def accept_frame(frame, acknowledge):
    match = ACK.fullmatch(frame)
    if match is None:
        LOG.warning("UART rejected: invalid frame")
        return
    trip = UUID(match["trip"].decode("ascii"))
    station = int(match["station"])
    try:
        acknowledge(trip, station)
    except HTTPException as error:
        LOG.warning(
            "UART rejected: trip=%s station=%s HTTP %s %s",
            trip, station, error.status_code, error.detail,
        )
    else:
        LOG.info("UART accepted: trip=%s station=%s status=completed", trip, station)
