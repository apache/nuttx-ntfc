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

import os
import pty
import select
import threading

import pytest
import serial

from ntfc.coreconfig import CoreConfig
from ntfc.device.serial import DeviceSerial


@pytest.fixture
def serial_pair():
    fd1, fd2 = pty.openpty()
    fd2_name = os.ttyname(fd2)
    return fd1, fd2_name


g_fake_device_retval = b""


def fake_device_thread(fd, stop):
    # read garbage
    # data = os.read(fd, 100)

    while not stop.is_set():
        try:
            rlist, _, _ = select.select([fd], [], [], 0.2)
            if rlist:
                _ = os.read(fd, 100)
                os.write(fd, g_fake_device_retval)
        except OSError:  # pragma: no cover
            break


@pytest.fixture
def serial_config():
    config = {
        "name": "main",
        "device": "serial",
        "exec_path": "",
        "exec_args": "",
        "conf_path": "",
        "elf_path": "",
    }

    return CoreConfig(config)


def test_device_sim_internals(serial_config, serial_pair):

    ser = DeviceSerial(serial_config)
    assert ser.name == "serial"
    assert ser.notalive is True

    # stop on non-started device is a no-op
    ser.stop()

    with pytest.raises(ValueError):
        _ = ser._decode_exec_args("aaaa")

    assert ser._decode_exec_args("1,n,8,1.5") == {
        "baudrate": 1,
        "bytesize": 8,
        "parity": "N",
        "stopbits": 1.5,
    }

    assert ser._dev_is_health_priv() is False
    assert ser._read() == b""
    assert ser._write_ctrl("a") is None
    assert ser._write(b"a") is None


def test_device_sim_init(serial_config, serial_pair):

    ser = DeviceSerial(serial_config)

    # no path and args
    with pytest.raises(serial.serialutil.SerialException):
        serial_config._config["exec_path"] = ""
        serial_config._config["exec_args"] = ""
        ser.start()

    # no boot
    with pytest.raises(TimeoutError):
        serial_config._config["exec_path"] = serial_pair[1]
        serial_config._config["exec_args"] = ""
        ser.start()

    stop = threading.Event()
    device_thread = threading.Thread(
        target=fake_device_thread, args=(serial_pair[0], stop)
    )
    device_thread.start()

    global g_fake_device_retval
    g_fake_device_retval = b"\n\rnsh>"
    ser.start()
    assert ser.notalive is False

    g_fake_device_retval = b""
    assert ser._write(b"a") is None
    assert ser._write_ctrl("a") is None

    # hard reboot/poweroff: no system command configured -> False
    assert ser.reboot() is False
    assert ser.poweroff() is False

    # soft reboot: device must respond with prompt for boot wait to succeed
    g_fake_device_retval = b"\n\rnsh>"
    assert ser.reboot(hard=False) is True

    # soft poweroff: sends OS command, no boot wait required
    assert ser.poweroff(hard=False) is True

    stop.set()
    device_thread.join(timeout=1)


def test_device_serial_boot_timeout(serial_pair, monkeypatch):

    config = CoreConfig(
        {
            "name": "main",
            "device": "serial",
            "exec_path": serial_pair[1],
            "boot_timeout": 9,
        }
    )
    ser = DeviceSerial(config)

    boot_timeouts = []

    def fake_wait(timeout=5):
        boot_timeouts.append(timeout)
        return True

    monkeypatch.setattr(ser, "_wait_for_boot", fake_wait)
    monkeypatch.setattr(ser, "reboot", lambda *args, **kwargs: True)

    ser._start_impl()
    ser.stop()

    # boot wait uses the configured boot_timeout
    assert boot_timeouts == [9]
