############################################################################
# SPDX-License-Identifier: Apache-2.0
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.  The
# ASF licenses this file to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance with the
# License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
# License for the specific language governing permissions and limitations
# under the License.
#
############################################################################

import socket
import struct
import time

import pytest

from ntfc.coreconfig import CoreConfig
from ntfc.device import netconsole
from ntfc.device.netconsole import (
    NetConsoleIsotp,
    NetConsoleUdp,
    get_netconsole,
)


def _wait_read(con, timeout=2.0):
    deadline = time.monotonic() + timeout
    data = b""
    while time.monotonic() < deadline:
        data += con.read()
        if data:
            return data
        time.sleep(0.01)
    return data


def test_netconsole_config():
    assert CoreConfig({"name": "t"}).netconsole is None

    cfg = {"type": "udp", "port": 1234}
    assert CoreConfig({"name": "t", "netconsole": cfg}).netconsole == cfg

    with pytest.raises(TypeError):
        _ = CoreConfig({"name": "t", "netconsole": "udp"}).netconsole


def test_get_netconsole():
    assert get_netconsole(None) is None
    assert get_netconsole({}) is None
    assert isinstance(get_netconsole({"type": "udp"}), NetConsoleUdp)
    assert isinstance(get_netconsole({"type": "isotp"}), NetConsoleIsotp)

    with pytest.raises(ValueError):
        get_netconsole({"type": "tcp"})

    with pytest.raises(ValueError):
        get_netconsole({"type": "udp", "chunk": 0})


def test_netconsole_udp():
    con = NetConsoleUdp({"type": "udp", "bind": "127.0.0.1", "port": 0})

    # closed transport is a no-op
    assert con.is_open is False
    assert con.read() == b""
    assert con.write(b"x") is None
    con.stop()

    con.start()
    assert con.is_open is True
    # second open keeps the socket
    sock = con._sock
    con.start()
    assert con._sock is sock

    port = con._sock.getsockname()[1]
    target = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target.bind(("127.0.0.1", 0))
    target.settimeout(2)

    # no data yet, and nowhere to send to
    assert _wait_read(con, 0.05) == b""
    con.write(b"dropped\n")

    # the target speaks first, the host learns its address
    target.sendto(b"nsh> ", ("127.0.0.1", port))
    assert _wait_read(con) == b"nsh> "
    assert con._peer == target.getsockname()

    # writes are split into chunks
    con._chunk = 4
    con.write(b"hello\n")
    assert target.recv(64) == b"hell"
    assert target.recv(64) == b"o\n"

    target.close()
    con.stop()
    assert con.is_open is False


def test_netconsole_read_errors(monkeypatch):
    con = NetConsoleUdp({"type": "udp", "bind": "127.0.0.1", "port": 0})
    con.start()
    monkeypatch.setattr(
        netconsole.select, "select", lambda r, w, x, t: (r, w, x)
    )

    def would_block():
        raise BlockingIOError

    monkeypatch.setattr(con, "_recv", would_block)
    assert con.read() == b""

    def failed():
        raise ConnectionRefusedError

    monkeypatch.setattr(con, "_recv", failed)
    assert con.read() == b""
    con.stop()


def test_netconsole_write_timeout(monkeypatch):
    con = NetConsoleUdp({"type": "udp", "bind": "127.0.0.1", "port": 0})
    con.start()
    con._peer = ("127.0.0.1", 9)
    sent = []
    monkeypatch.setattr(con, "_send", sent.append)

    # the previous datagram never left: the write is dropped
    monkeypatch.setattr(
        netconsole.select, "select", lambda r, w, x, t: ([], [], [])
    )
    con.write(b"help\n")
    assert sent == []
    con.stop()


class FakeIsotpSocket:
    def __init__(self, family, kind, proto, fail_bind=False):
        self.args = (family, kind, proto)
        self.opts = []
        self.bound = None
        self.sent = []
        self.closed = False
        self.blocking = True
        self.fail_bind = fail_bind
        self.rx = [b"nsh> "]

    def setsockopt(self, level, opt, value):
        self.opts.append((level, opt, value))

    def bind(self, addr):
        if self.fail_bind:
            raise OSError("no such device")
        self.bound = addr

    def setblocking(self, flag):
        self.blocking = flag

    def send(self, data):
        self.sent.append(data)

    def recv(self, size):
        return self.rx.pop(0)

    def close(self):
        self.closed = True


def test_netconsole_isotp(monkeypatch):
    socks = []

    def factory(family, kind, proto=0):
        sock = FakeIsotpSocket(family, kind, proto)
        socks.append(sock)
        return sock

    monkeypatch.setattr(netconsole.socket, "socket", factory)
    monkeypatch.setattr(
        netconsole.select,
        "select",
        lambda r, w, x, t: ([s for s in r if s.rx], w, x),
    )

    # classic CAN with the default CAN IDs
    con = get_netconsole({"type": "isotp"})
    con.start()
    sock = socks[-1]
    assert sock.args[1] == socket.SOCK_DGRAM
    assert sock.bound == ("can0", 2000, 2001)
    assert sock.opts == []
    assert sock.blocking is False

    assert con.read() == b"nsh> "
    con._chunk = 3
    con.write(b"help\n")
    assert sock.sent == [b"hel", b"p\n"]
    con.stop()
    assert sock.closed is True

    # CAN FD link layer
    con = get_netconsole(
        {
            "type": "isotp",
            "interface": "vcan1",
            "rx_id": 0x123,
            "tx_id": 0x321,
            "fd": True,
        }
    )
    con.start()
    sock = socks[-1]
    assert sock.bound == ("vcan1", 0x123, 0x321)
    assert sock.opts == [
        (
            NetConsoleIsotp.SOL_CAN_ISOTP,
            NetConsoleIsotp.CAN_ISOTP_LL_OPTS,
            struct.pack("=BBB", 72, 64, 0),
        )
    ]
    con.stop()


def test_netconsole_isotp_bind_error(monkeypatch):
    socks = []

    def factory(family, kind, proto=0):
        sock = FakeIsotpSocket(family, kind, proto, fail_bind=True)
        socks.append(sock)
        return sock

    monkeypatch.setattr(netconsole.socket, "socket", factory)

    con = get_netconsole({"type": "isotp"})
    with pytest.raises(OSError):
        con.start()

    assert socks[-1].closed is True
    assert con.is_open is False
