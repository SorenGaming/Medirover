from threading import Event
from uuid import uuid4

import pytest
from fastapi import HTTPException

from uart import Base, accept_frame, read_frames


class FakePort:

    def __init__(self, base, answer):
        self.base, self.answer, self.written = base, answer, []

    def write(self, data):
        self.written.append(data)
        if self.answer:
            trip = data.decode().split(",")[1].strip()
            self.base.accept(self.answer.format(trip=trip).encode())


def test_command_waits_for_ok_or_nak():
    events = []
    base = Base("fake", lambda *args: events.append(args), None)
    trip = uuid4()
    with pytest.raises(HTTPException) as error:
        base.command(f"KLAR,{trip}", trip)
    assert error.value.status_code == 503

    base.port = FakePort(base, "OK,{trip}\r\n")
    base.command(f"ORDER,{trip},1", trip)
    assert base.port.written == [f"ORDER,{trip},1\n".encode()]

    base.port = FakePort(base, "NAK,{trip},NOT_HOME\r\n")
    with pytest.raises(HTTPException) as error:
        base.command(f"ORDER,{trip},1", trip)
    assert error.value.status_code == 409 and error.value.detail.endswith("NOT_HOME")

    base.port = FakePort(base, None)
    with pytest.raises(HTTPException) as error:
        base.command(f"STOP,{trip}", trip, timeout=0.05)
    assert error.value.status_code == 504
    assert events == []


def test_events_and_lines_the_server_does_not_use():
    events = []
    trip = uuid4()
    for frame in (f"STARTED,{trip},1\r\n", f"ERR,{trip},STOPPED\n", f"HOME,{trip}\n",
                  "# BIL: kryds: drejer venstre\r\n", f"LID,{trip},R,OPEN\n", "ERR,-,LINE\n",
                  "HOME,not-a-trip\n", f"ACK,{trip},1"):
        accept_frame(frame.encode(), lambda *args: events.append(args))
    assert events == [("STARTED", trip, "1"), ("ERR", trip, "STOPPED"), ("HOME", trip, None)]


def test_reader_splits_lines_and_drops_long_ones():
    class Bytes:
        def __init__(self, data):
            self.data = list(data)

        def read(self):
            if not self.data:
                stop.set()
                return b""
            return bytes([self.data.pop(0)])

    stop = Event()
    lines = []
    read_frames(Bytes(b"OK,a\r\n" + b"X" * 80 + b"\nHOME,b\n"), stop, lines.append)
    assert lines == [b"OK,a\r\n", b"HOME,b\n"]
