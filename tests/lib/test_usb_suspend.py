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

import errno
import os
import types

import pytest

from ntfc.lib.usb import suspend
from ntfc.lib.usb.suspend import (
    CycleResult,
    StreamRead,
    UsbPower,
    UsbSuspendCheck,
    UsbSuspendConfig,
    UsbSuspendError,
    autodetect,
    console_probe,
    find_cdc_ports,
    port_holders,
    read_attr,
    read_stream,
    require_free_port,
    usb_device_dir,
)


class FakeClock:
    """Deterministic replacement for the module ``time`` import."""

    def __init__(self, step=0.5):
        self.now = 0.0
        self.step = step

    def time(self):
        value = self.now
        self.now += self.step
        return value

    def sleep(self, seconds):
        self.now += seconds


class FakePort:
    def __init__(self, chunks=None):
        self.chunks = list(chunks or [])
        self.written = b""
        self.closed = False
        self.flushed = 0
        self.reset = 0

    def read(self, _size):
        return self.chunks.pop(0) if self.chunks else b""

    def write(self, data):
        self.written += data

    def flush(self):
        self.flushed += 1

    def reset_input_buffer(self):
        self.reset += 1

    def close(self):
        self.closed = True


def fake_serial(port=None, error=None):
    """Build a stand-in for the ``serial`` module."""

    def factory(*_args, **_kwargs):
        if error is not None:
            raise error
        return port if port is not None else FakePort()

    return types.SimpleNamespace(Serial=factory)


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


@pytest.fixture
def sysfs(tmp_path, monkeypatch):
    """Build a fake sysfs/devfs holding one CDC/ACM device."""
    root = str(tmp_path)
    usbdir = os.path.join(root, "sys/devices/usb1/1-5")
    iface = os.path.join(usbdir, "1-5:1.0")

    write_file(os.path.join(usbdir, "idVendor"), "3185\n")
    write_file(os.path.join(usbdir, "idProduct"), "0039\n")
    write_file(os.path.join(usbdir, "product"), "ARK FMU v6X.x\n")
    write_file(os.path.join(usbdir, "power/control"), "auto\n")
    write_file(os.path.join(usbdir, "power/autosuspend_delay_ms"), "2000\n")
    write_file(os.path.join(usbdir, "power/runtime_status"), "active\n")
    os.makedirs(iface, exist_ok=True)

    tty = os.path.join(root, "sys/class/tty/ttyACM0")
    os.makedirs(tty, exist_ok=True)
    os.symlink(iface, os.path.join(tty, "device"))

    dev = os.path.join(root, "dev/ttyACM0")
    write_file(dev, "")

    byid = os.path.join(root, "dev/serial/by-id")
    os.makedirs(byid, exist_ok=True)
    os.symlink(dev, os.path.join(byid, "usb-ARK_FMU_v6X-if00"))

    monkeypatch.setattr(
        suspend, "SYSFS_TTY", os.path.join(root, "sys/class/tty")
    )
    monkeypatch.setattr(suspend, "DEV_SERIAL_BY_ID", byid)
    monkeypatch.setattr(suspend, "PROCFS", os.path.join(root, "proc"))

    return types.SimpleNamespace(
        root=root, usbdir=usbdir, dev=dev, byid=byid, tty=tty
    )


###############################################################################
# sysfs helpers
###############################################################################


def test_read_attr(sysfs):
    assert read_attr(sysfs.usbdir, "idVendor") == "3185"
    assert read_attr(sysfs.usbdir, "nosuchattr") is None


def test_usb_device_dir(sysfs):
    assert usb_device_dir(sysfs.dev) == sysfs.usbdir


def test_usb_device_dir_not_a_tty(sysfs):
    with pytest.raises(UsbSuspendError, match="not a tty backed by sysfs"):
        usb_device_dir(os.path.join(sysfs.root, "dev/ttyS9"))


def test_usb_device_dir_not_on_usb(sysfs):
    plain = os.path.join(sysfs.root, "sys/devices/platform/serial0")
    os.makedirs(plain, exist_ok=True)
    tty = os.path.join(sysfs.root, "sys/class/tty/ttyS0")
    os.makedirs(tty, exist_ok=True)
    os.symlink(plain, os.path.join(tty, "device"))

    dev = os.path.join(sysfs.root, "dev/ttyS0")
    write_file(dev, "")

    with pytest.raises(UsbSuspendError, match="no idVendor in any parent"):
        usb_device_dir(dev)


def test_find_cdc_ports_skips_non_cdc_and_non_usb(sysfs):
    # A non-CDC port: filtered on the tty name alone.
    other = os.path.join(sysfs.root, "dev/ttyUSB0")
    write_file(other, "")
    os.symlink(other, os.path.join(sysfs.byid, "usb-FTDI-if00"))

    # A CDC port that is not backed by sysfs: dropped by usb_device_dir().
    orphan = os.path.join(sysfs.root, "dev/ttyACM9")
    write_file(orphan, "")
    os.symlink(orphan, os.path.join(sysfs.byid, "usb-Orphan-if00"))

    assert find_cdc_ports() == [
        (os.path.join(sysfs.byid, "usb-ARK_FMU_v6X-if00"), sysfs.usbdir)
    ]


def test_autodetect(sysfs):
    assert autodetect() == os.path.join(sysfs.byid, "usb-ARK_FMU_v6X-if00")


def test_autodetect_nothing(sysfs, monkeypatch):
    monkeypatch.setattr(
        suspend, "DEV_SERIAL_BY_ID", str(sysfs.root) + "/empty"
    )
    with pytest.raises(UsbSuspendError, match="no CDC/ACM port found"):
        autodetect()


def test_autodetect_ambiguous(sysfs):
    second = os.path.join(sysfs.root, "sys/class/tty/ttyACM1")
    os.makedirs(second, exist_ok=True)
    os.symlink(
        os.path.join(sysfs.usbdir, "1-5:1.0"), os.path.join(second, "device")
    )

    dev = os.path.join(sysfs.root, "dev/ttyACM1")
    write_file(dev, "")
    os.symlink(dev, os.path.join(sysfs.byid, "usb-Second-if00"))

    with pytest.raises(UsbSuspendError, match="ARK FMU v6X.x"):
        autodetect()


###############################################################################
# port ownership
###############################################################################


def test_port_holders(sysfs):
    proc = os.path.join(sysfs.root, "proc")
    real = os.path.realpath(sysfs.dev)

    os.makedirs(os.path.join(proc, "123/fd"), exist_ok=True)
    os.symlink(real, os.path.join(proc, "123/fd/3"))
    write_file(os.path.join(proc, "123/comm"), "cat\n")

    # Exited between the readlink() and the comm read.
    os.makedirs(os.path.join(proc, "456/fd"), exist_ok=True)
    os.symlink(real, os.path.join(proc, "456/fd/3"))

    # Holds something else.
    os.makedirs(os.path.join(proc, "789/fd"), exist_ok=True)
    os.symlink("/dev/null", os.path.join(proc, "789/fd/1"))

    # Not a symlink at all.
    write_file(os.path.join(proc, "999/fd/0"), "")

    assert port_holders(sysfs.dev) == [("123", "cat")]


def test_require_free_port_ok(sysfs, monkeypatch):
    monkeypatch.setattr(suspend, "serial", fake_serial())
    require_free_port(sysfs.dev, 115200)


def test_require_free_port_busy(sysfs, monkeypatch):
    monkeypatch.setattr(
        suspend, "serial", fake_serial(error=OSError(errno.EBUSY, "busy"))
    )
    with pytest.raises(UsbSuspendError, match="held open by another process"):
        require_free_port(sysfs.dev, 115200)


def test_require_free_port_unopenable(sysfs, monkeypatch):
    monkeypatch.setattr(
        suspend, "serial", fake_serial(error=OSError(errno.EACCES, "denied"))
    )
    with pytest.raises(UsbSuspendError, match="cannot open"):
        require_free_port(sysfs.dev, 115200)


###############################################################################
# measurement
###############################################################################


def test_read_stream_counts_tail(sysfs, monkeypatch):
    port = FakePort([b"a" * 100, b"b" * 200, b"c" * 300])
    monkeypatch.setattr(suspend, "serial", fake_serial(port=port))
    monkeypatch.setattr(suspend, "time", FakeClock())

    result = read_stream(sysfs.dev, 115200, 2.0, 1.0)

    assert result.total == 600
    assert result.tail == 500
    assert result.error == ""
    assert port.closed


def test_read_stream_open_error(sysfs, monkeypatch):
    monkeypatch.setattr(suspend, "serial", fake_serial(error=OSError("gone")))
    assert read_stream(sysfs.dev, 115200, 2.0, 1.0).error == "gone"


def test_console_probe_ok(monkeypatch):
    port = FakePort([b"nsh> echo probe > /dev/ttyACM0\nnsh> "])
    monkeypatch.setattr(suspend, "serial", fake_serial(port=port))
    monkeypatch.setattr(suspend, "time", FakeClock())

    assert console_probe("/dev/ttyUSB0", 57600, "/dev/ttyACM0") == (
        "board-side open ok"
    )
    assert b"echo probe > /dev/ttyACM0\n" in port.written
    assert port.closed


@pytest.mark.parametrize(
    "reply",
    [
        b"nsh: echo: open failed: Transport endpoint is not connected\n",
        b"cdcacm: ENOTCONN\n",
    ],
)
def test_console_probe_enotconn(monkeypatch, reply):
    monkeypatch.setattr(suspend, "serial", fake_serial(port=FakePort([reply])))
    monkeypatch.setattr(suspend, "time", FakeClock())

    assert console_probe("/dev/ttyUSB0", 57600, "/dev/ttyACM0") == (
        "board-side open failed: -ENOTCONN"
    )


def test_console_probe_other_failure(monkeypatch):
    port = FakePort([b"nsh: echo: open failed: No such file\n"])
    monkeypatch.setattr(suspend, "serial", fake_serial(port=port))
    monkeypatch.setattr(suspend, "time", FakeClock())

    assert console_probe("/dev/ttyUSB0", 57600, "/dev/ttyACM0").startswith(
        "board-side open failed: nsh:"
    )


def test_console_probe_unavailable(monkeypatch):
    monkeypatch.setattr(suspend, "serial", fake_serial(error=OSError("nope")))
    assert console_probe("/dev/ttyUSB0", 57600, "/dev/ttyACM0") == (
        "console unavailable (nope)"
    )


###############################################################################
# runtime PM
###############################################################################


class FakeRun:
    def __init__(self, returncode=0, stderr=b""):
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def __call__(self, cmd, **kwargs):
        payload = kwargs["input"].decode()
        self.calls.append((cmd[-1], payload))
        if self.returncode == 0:
            write_file(cmd[-1], payload)
        return types.SimpleNamespace(
            returncode=self.returncode, stderr=self.stderr
        )


def test_usbpower_get_set_restore(sysfs, monkeypatch):
    run = FakeRun()
    monkeypatch.setattr(suspend.subprocess, "run", run)

    power = UsbPower(sysfs.usbdir)
    assert power.saved == {"control": "auto", "autosuspend_delay_ms": "2000"}

    power.set_attr("control", "on")
    assert power.get_attr("control") == "on"

    # A missing attribute is never restored.
    power.saved["nosuchattr"] = None
    power.restore()
    assert power.get_attr("control") == "auto"
    assert "nosuchattr" not in [name for name, _ in run.calls]


def test_usbpower_set_refused(sysfs, monkeypatch):
    monkeypatch.setattr(
        suspend.subprocess, "run", FakeRun(1, b"tee: Permission denied\n")
    )
    with pytest.raises(UsbSuspendError, match="Permission denied"):
        UsbPower(sysfs.usbdir).set_attr("control", "on")


def test_usbpower_arm(sysfs, monkeypatch):
    run = FakeRun()
    monkeypatch.setattr(suspend.subprocess, "run", run)

    UsbPower(sysfs.usbdir).arm(1000)

    assert [value for _, value in run.calls] == ["1000", "on", "auto"]


def test_usbpower_wait_suspended(sysfs, monkeypatch):
    monkeypatch.setattr(suspend, "time", FakeClock())
    power = UsbPower(sysfs.usbdir)

    assert power.wait_suspended(0.0) is False

    write_file(os.path.join(sysfs.usbdir, "power/runtime_status"), "suspended")
    assert power.wait_suspended(10.0) is True


###############################################################################
# the check itself
###############################################################################


@pytest.fixture
def check(sysfs, monkeypatch):
    monkeypatch.setattr(suspend, "serial", fake_serial())
    monkeypatch.setattr(suspend, "time", FakeClock())
    monkeypatch.setattr(suspend.subprocess, "run", FakeRun())
    return UsbSuspendCheck(UsbSuspendConfig(device=sysfs.dev, cycles=2))


def test_check_autodetects_device(sysfs, monkeypatch):
    monkeypatch.setattr(suspend, "serial", fake_serial())
    check = UsbSuspendCheck(UsbSuspendConfig())
    assert check.usbdir == sysfs.usbdir


def test_check_report(check, capsys):
    check.report_setup()
    check.report_cycle(1, CycleResult(True, StreamRead(40898, 23316), "ok"))
    check.report_cycle(2, CycleResult(False, StreamRead(error="EIO")))

    out = capsys.readouterr().out
    assert "3185:0039  ARK FMU v6X.x" in out
    assert "read=40898   tail=23316   ok" in out
    assert "OPEN FAILED: EIO" in out


def test_check_cycle_probes_console(check, sysfs, monkeypatch):
    write_file(os.path.join(sysfs.usbdir, "power/runtime_status"), "suspended")
    check.cfg.console = "/dev/ttyUSB0"

    result = check.cycle()

    assert result.suspended is True
    assert result.note == "board-side open ok"


def test_check_cycle_without_console(check):
    assert check.cycle().note == ""


def test_check_verdict_inconclusive(check, capsys):
    assert check.verdict([CycleResult(False)]) == 2
    assert "INCONCLUSIVE" in capsys.readouterr().out


def test_check_verdict_pass(check, capsys):
    results = [CycleResult(True, StreamRead(40898, 23316)) for _ in range(2)]
    assert check.verdict(results) == 0
    assert "PASS" in capsys.readouterr().out


def test_check_verdict_fail(check, capsys):
    results = [
        CycleResult(True, StreamRead(12179, 0)),
        CycleResult(True, StreamRead(0, 0)),
    ]
    assert check.verdict(results) == 1
    assert "FAIL" in capsys.readouterr().out


def test_check_run_restores_power(check, sysfs, capsys):
    write_file(os.path.join(sysfs.usbdir, "power/runtime_status"), "suspended")

    assert check.run() == 1

    assert check.power.get_attr("control") == "auto"
    assert "restored to control=auto" in capsys.readouterr().out
