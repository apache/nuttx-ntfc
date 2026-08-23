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

import pytest
from click.testing import CliRunner

from ntfc.cli.main import main
from ntfc.lib.usb.suspend import UsbSuspendError

ARGS = [
    "usb-suspend",
    "--device=/dev/ttyACM0",
    "--cycles=3",
    "--delay-ms=500",
    "--baud=57600",
    "--read-secs=1.0",
    "--tail-secs=0.5",
    "--min-bytes=100",
    "--console=/dev/ttyUSB0",
    "--console-baud=57600",
    "--cdc-path=/dev/ttyACM1",
]


@pytest.fixture
def runner():
    return CliRunner()


def fake_check(ret=None, exc=None):
    class FakeUsbSuspendCheck:
        def __init__(self, cfg):
            if exc is not None:
                raise exc
            self.cfg = cfg

        def run(self):
            return ret

    return FakeUsbSuspendCheck


def test_usbsuspend_pass(runner, monkeypatch):
    captured = {}

    class Recorder(fake_check(ret=0)):
        def __init__(self, cfg):
            super().__init__(cfg)
            captured["cfg"] = cfg

    monkeypatch.setattr("ntfc.cli.main.UsbSuspendCheck", Recorder)

    result = runner.invoke(main, ARGS)

    assert result.exit_code == 0
    cfg = captured["cfg"]
    assert cfg.device == "/dev/ttyACM0"
    assert cfg.cycles == 3
    assert cfg.delay_ms == 500
    assert cfg.baud == 57600
    assert cfg.read_secs == 1.0
    assert cfg.tail_secs == 0.5
    assert cfg.min_bytes == 100
    assert cfg.console == "/dev/ttyUSB0"
    assert cfg.console_baud == 57600
    assert cfg.cdc_path == "/dev/ttyACM1"


def test_usbsuspend_fail(runner, monkeypatch):
    monkeypatch.setattr("ntfc.cli.main.UsbSuspendCheck", fake_check(ret=1))
    assert runner.invoke(main, ["usb-suspend"]).exit_code == 1


def test_usbsuspend_error(runner, monkeypatch):
    monkeypatch.setattr(
        "ntfc.cli.main.UsbSuspendCheck",
        fake_check(exc=UsbSuspendError("no CDC/ACM port found")),
    )

    result = runner.invoke(main, ["usb-suspend"])

    assert result.exit_code == 1
    assert "no CDC/ACM port found" in result.output
