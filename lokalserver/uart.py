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
TEMPERATURE = re.compile(rb"TEMP,rover,(?P<celsius>-?\d{1,3}(?:\.\d{1,2})?)\r?\n")


def read_receipts(port, stop, acknowledge, temperature_callback=None):
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
                    accept_frame(frame, acknowledge, temperature_callback)
                frame.clear()
                discard = False
            elif len(frame) >= MAX_FRAME:
                frame.clear()
                discard = True
    except SerialException:
        LOG.exception("UART reader stopped")


def accept_frame(frame, acknowledge, temperature_callback=None):
    measurement = TEMPERATURE.fullmatch(frame)
    if measurement is not None:
        value = float(measurement["celsius"])
        if temperature_callback is None or not -100 <= value <= 150:
            LOG.warning("UART rejected: temperature receiver unavailable or invalid value")
            return
        try:
            temperature_callback(value)
        except HTTPException:
            LOG.warning("UART rejected: temperature storage unavailable")
        else:
            LOG.info("UART temperature stored: %.2f C", value)
        return
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
