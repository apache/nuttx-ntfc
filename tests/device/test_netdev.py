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
import subprocess
import sys

import pytest

from ntfc.coreconfig import CoreConfig
from ntfc.device.getdev import get_device
from ntfc.device.netdev import DeviceNetdev

TARGET = "./tests/resources/netconsole/udp_target.py"


def _port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _conf(port, **extra):
    cfg = {
        "name": "t",
        "device": "netdev",
        "prompt": "nsh> ",
        "boot_timeout": 5,
        "netconsole": {"type": "udp", "bind": "127.0.0.1", "port": port},
    }
    cfg.update(extra)
    return CoreConfig(cfg)


def test_device_netdev_needs_netconsole():
    with pytest.raises(ValueError):
        DeviceNetdev(CoreConfig({"name": "t", "device": "netdev"}))


def test_device_netdev(monkeypatch):
    port = _port()
    dev = get_device(_conf(port))
    assert isinstance(dev, DeviceNetdev)
    assert dev.name == "netdev"

    # not started: unhealthy, I/O is a no-op, no reboot/poweroff command
    assert dev.notalive is True
    assert dev._dev_is_health_priv() is False
    assert dev._read() == b""
    assert dev._write(b"a") is None
    assert dev._write_ctrl("C") is None
    assert dev._reboot_impl() is False
    assert dev._poweroff_impl() is False

    # the board boots after the transport is up, like after a reset
    dev._con.start()
    target = subprocess.Popen([sys.executable, TARGET, str(port)])
    try:
        dev.start()
        assert dev.notalive is False

        ret = dev.send_command(b"hello", 1)
        assert b"Hello, World!" in ret
        assert dev.send_ctrl_cmd("C") == 0
    finally:
        dev.stop()
        target.kill()
        target.wait()

    assert dev.notalive is True


def test_device_netdev_boot_timeout():
    dev = get_device(_conf(_port(), boot_timeout=1))
    with pytest.raises(TimeoutError):
        dev.start()
    dev.stop()


def test_device_netdev_system_commands(monkeypatch):
    dev = get_device(_conf(_port(), reboot="reset-board", poweroff="off"))
    cmds = []
    monkeypatch.setattr(dev, "_system_cmd", cmds.append)

    assert dev._reboot_impl() is True
    assert dev._poweroff_impl() is True
    assert cmds == ["reset-board", "off"]
