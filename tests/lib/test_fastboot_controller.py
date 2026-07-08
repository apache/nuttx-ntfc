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

from ntfc.lib.fastboot.controller import FastbootController


def _ctrl(dev_sn: str = "ABC123") -> FastbootController:
    return FastbootController(dev_sn)


def _run_ok() -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = b""
    return m


def _run_fail() -> MagicMock:
    m = MagicMock()
    m.returncode = 1
    m.stdout = b"FAILED\n"
    return m


class TestFastbootControllerIsConnected:
    def test_true_when_dev_sn_in_output(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"ABC123\tfastboot\n", returncode=0
            )
            assert _ctrl().is_connected() is True

    def test_false_when_dev_sn_not_in_output(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"OTHER\tfastboot\n", returncode=0
            )
            assert _ctrl().is_connected() is False

    def test_false_when_output_empty(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"", returncode=0)
            assert _ctrl().is_connected() is False

    def test_false_on_timeout_expired(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="fastboot", timeout=10),
        ):
            assert _ctrl().is_connected() is False

    def test_false_on_oserror(self) -> None:
        with patch(
            "subprocess.run", side_effect=OSError("fastboot not found")
        ):
            assert _ctrl().is_connected() is False

    def test_false_when_dev_sn_empty_even_with_devices_listed(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=b"ABC123\tfastboot\n", returncode=0
            )
            assert _ctrl(dev_sn="").is_connected() is False
            mock_run.assert_not_called()


class TestFastbootControllerMemdump:
    def test_returns_path_on_success(self, tmp_path: "Path") -> None:
        with patch("subprocess.run", return_value=_run_ok()):
            result = _ctrl().memdump(
                "0x40000000", "0x08000000", tmp_path / "core.bin"
            )
        assert result == tmp_path / "core.bin"

    def test_creates_parent_directory(self, tmp_path: "Path") -> None:
        nested = tmp_path / "sub" / "dir" / "core.bin"
        with patch("subprocess.run", return_value=_run_ok()):
            _ctrl().memdump("0x40000000", "0x08000000", nested)
        assert nested.parent.is_dir()

    def test_returns_none_when_memdump_fails(self, tmp_path: "Path") -> None:
        with patch("subprocess.run", return_value=_run_fail()):
            result = _ctrl().memdump(
                "0x40000000", "0x08000000", tmp_path / "core.bin"
            )
        assert result is None

    def test_returns_none_when_get_staged_fails(
        self, tmp_path: "Path"
    ) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [_run_ok(), _run_fail()]
            result = _ctrl().memdump(
                "0x40000000", "0x08000000", tmp_path / "core.bin"
            )
        assert result is None

    def test_passes_addr_and_size_to_command(self, tmp_path: "Path") -> None:
        ctrl = FastbootController("DEV1")
        with patch("subprocess.run", return_value=_run_ok()) as mock_run:
            ctrl.memdump("0x20000000", "0x04000000", tmp_path / "core.bin")
        memdump_cmd = mock_run.call_args_list[0][0][0]
        assert "0x20000000" in memdump_cmd
        assert "0x04000000" in memdump_cmd

    def test_uses_dev_sn_in_commands(self, tmp_path: "Path") -> None:
        ctrl = FastbootController("MYDEVICE")
        with patch("subprocess.run", return_value=_run_ok()) as mock_run:
            ctrl.memdump("0x40000000", "0x08000000", tmp_path / "core.bin")
        for c in mock_run.call_args_list:
            assert "MYDEVICE" in c[0][0]

    def test_returns_none_on_timeout(self, tmp_path: "Path") -> None:
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="fastboot", timeout=30),
        ):
            result = _ctrl().memdump(
                "0x40000000", "0x08000000", tmp_path / "core.bin"
            )
        assert result is None

    def test_returns_none_on_oserror(self, tmp_path: "Path") -> None:
        with patch(
            "subprocess.run", side_effect=OSError("fastboot not found")
        ):
            result = _ctrl().memdump(
                "0x40000000", "0x08000000", tmp_path / "core.bin"
            )
        assert result is None


class TestFastbootControllerRun:
    def test_returns_true_on_success(self) -> None:
        with patch("subprocess.run", return_value=_run_ok()):
            assert _ctrl().run(["oem", "test"], timeout=10.0) is True

    def test_returns_false_on_nonzero_exit(self) -> None:
        with patch("subprocess.run", return_value=_run_fail()):
            assert _ctrl().run(["oem", "test"], timeout=10.0) is False

    def test_returns_false_on_timeout(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="fastboot", timeout=10),
        ):
            assert _ctrl().run(["oem", "test"], timeout=10.0) is False

    def test_returns_false_on_oserror(self) -> None:
        with patch(
            "subprocess.run", side_effect=OSError("fastboot not found")
        ):
            assert _ctrl().run(["oem", "test"], timeout=10.0) is False

    def test_includes_dev_sn_in_command(self) -> None:
        ctrl = FastbootController("SN123")
        with patch("subprocess.run", return_value=_run_ok()) as mock_run:
            ctrl.run(["oem", "test"], timeout=10.0)
        cmd = mock_run.call_args[0][0]
        assert "SN123" in cmd
