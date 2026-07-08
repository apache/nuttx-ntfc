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

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

from ntfc.lib.ymodem.controller import YmodemController


def _run_ok(output: str = "sbrb success\n") -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = output.encode()
    return m


def _run_fail() -> MagicMock:
    m = MagicMock()
    m.returncode = 1
    m.stdout = b"sbrb failed\n"
    return m


class TestYmodemControllerIsReady:
    def test_true_when_configured(self, tmp_path: "Path") -> None:
        sbrb = tmp_path / "sbrb.py"
        sbrb.write_text("x")
        ctrl = YmodemController("/dev/ttyUSB0", sbrb)
        assert ctrl.is_ready() is True

    def test_false_when_sbrb_missing(self, tmp_path: "Path") -> None:
        ctrl = YmodemController("/dev/ttyUSB0", tmp_path / "missing.py")
        assert ctrl.is_ready() is False

    def test_false_when_serial_port_empty(self, tmp_path: "Path") -> None:
        sbrb = tmp_path / "sbrb.py"
        sbrb.write_text("x")
        ctrl = YmodemController("", sbrb)
        assert ctrl.is_ready() is False


class TestYmodemControllerDownload:
    def test_returns_true_on_success(self, tmp_path: "Path") -> None:
        sbrb = tmp_path / "sbrb.py"
        sbrb.write_text("x")
        ctrl = YmodemController("/dev/ttyUSB0", sbrb)
        with patch("subprocess.run", return_value=_run_ok()):
            assert ctrl.download(tmp_path, "app.core") is True

    def test_returns_false_when_sbrb_reports_failure(
        self, tmp_path: "Path"
    ) -> None:
        sbrb = tmp_path / "sbrb.py"
        sbrb.write_text("x")
        ctrl = YmodemController("/dev/ttyUSB0", sbrb)
        with patch("subprocess.run", return_value=_run_fail()):
            assert ctrl.download(tmp_path, "app.core") is False

    def test_returns_false_on_timeout(self, tmp_path: "Path") -> None:
        sbrb = tmp_path / "sbrb.py"
        sbrb.write_text("x")
        ctrl = YmodemController("/dev/ttyUSB0", sbrb)
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="sbrb.py", timeout=3600),
        ):
            assert ctrl.download(tmp_path, "app.core") is False

    def test_returns_false_on_oserror(self, tmp_path: "Path") -> None:
        sbrb = tmp_path / "sbrb.py"
        sbrb.write_text("x")
        ctrl = YmodemController("/dev/ttyUSB0", sbrb)
        with patch(
            "subprocess.run", side_effect=OSError("sbrb.py not executable")
        ):
            assert ctrl.download(tmp_path, "app.core") is False

    def test_passes_serial_port_and_baud_rate(self, tmp_path: "Path") -> None:
        sbrb = tmp_path / "sbrb.py"
        sbrb.write_text("x")
        ctrl = YmodemController("/dev/ttyUSB1", sbrb, baud_rate=115200)
        with patch("subprocess.run", return_value=_run_ok()) as mock_run:
            ctrl.download(tmp_path, "app.core")
        cmd = mock_run.call_args[0][0]
        assert "/dev/ttyUSB1" in cmd
        assert "115200" in cmd
