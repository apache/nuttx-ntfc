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
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ntfc.device.common import CmdReturn, CmdStatus, DeviceCommon
from ntfc.log.handler import LogHandler

g_mock_read = b""


class DeviceMock(DeviceCommon):

    def __init__(self, _):
        """Mock."""

        DeviceCommon.__init__(self, _)

    def _read(self, _=0):
        """Mock."""
        return g_mock_read

    def _write(self, _):
        """Mock."""

    def _write_ctrl(self, _):
        """Mock."""

    def _dev_is_health_priv(
        self,
    ):
        """Mock."""

    def _start_impl(self):
        """Mock."""

    def _stop_impl(self):
        """Mock."""

    def name(self):
        """Mock."""

    def notalive(self):
        """Mock."""

    def _poweroff_impl(self) -> bool:
        """Mock."""
        return False

    def _reboot_impl(self, timeout: int) -> bool:
        """Mock."""
        return False


def test_device_common_data():

    a = CmdStatus(0)
    assert a == 0
    assert str(a) == "SUCCESS"

    b = CmdReturn(0)
    c1, c2, c3 = b
    assert (c1, c2, c3) == (0, None, "")

    b = CmdReturn(-1, None, "test")
    c1, c2, c3 = b
    assert (c1, c2, c3) == (-1, None, "test")


def test_device_common_init():

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:
        config = mockdevice.return_value

        d = DeviceMock(config)
        assert d is not None

        assert d.crash is False
        assert d.busyloop is False
        assert d.flood is False


def test_device_common_send_cmd_pattern():

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:

        global g_mock_read

        config = mockdevice.return_value

        dev = DeviceMock(config)
        assert dev is not None

        assert dev.flood is False

        with tempfile.TemporaryDirectory() as tmpdir:
            h = LogHandler(tmpdir, "test")
            dev.start_log_collect(h)

            g_mock_read = b"x" * 10000
            ret = dev.send_cmd_read_until_pattern(b"", b"x", 1)
            assert ret.status == CmdStatus.SUCCESS

            g_mock_read = b"x" * 10000
            ret = dev.send_cmd_read_until_pattern(b"", b"y", 1)
            assert ret.status == CmdStatus.TIMEOUT

            assert dev.flood is True

            dev.stop_log_collect()
            h.close()

            device_path = os.path.join(
                tmpdir, "test" + LogHandler.DEVICE_SUFFIX
            )
            with open(device_path) as f:
                assert "fault detected: flood" in f.read()

        g_mock_read = b"x" * 10000
        ret = dev.send_cmd_read_until_pattern(b"", b"y", 1)
        assert ret.status == CmdStatus.TIMEOUT


def test_device_common_send_cmd_fail_pattern():

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:

        global g_mock_read

        config = mockdevice.return_value
        dev = DeviceMock(config)

        # fail_pattern detected before success pattern → FAILED, exits early
        g_mock_read = b"ERROR: something bad"
        ret = dev.send_cmd_read_until_pattern(
            b"", b"SUCCESS", 10, fail_pattern=b"ERROR"
        )
        assert ret.status == CmdStatus.FAILED

        # success pattern present, no fail_pattern → SUCCESS
        g_mock_read = b"SUCCESS"
        ret = dev.send_cmd_read_until_pattern(
            b"", b"SUCCESS", 10, fail_pattern=b"ERROR"
        )
        assert ret.status == CmdStatus.SUCCESS

        # neither pattern → TIMEOUT
        g_mock_read = b"normal output"
        ret = dev.send_cmd_read_until_pattern(
            b"", b"SUCCESS", 1, fail_pattern=b"ERROR"
        )
        assert ret.status == CmdStatus.TIMEOUT

        # no fail_pattern → behaves as before
        g_mock_read = b"SUCCESS"
        ret = dev.send_cmd_read_until_pattern(b"", b"SUCCESS", 10)
        assert ret.status == CmdStatus.SUCCESS


def test_device_common_decodes_invalid_utf8_with_replacement():
    with patch("ntfc.envconfig.EnvConfig") as mockdevice:
        global g_mock_read

        config = mockdevice.return_value
        dev = DeviceMock(config)

        g_mock_read = b"\xff\xfeOK"
        ret = dev.send_cmd_read_until_pattern(b"", b"OK", 1)

        assert ret.status == CmdStatus.SUCCESS
        assert "\ufffd" in ret.output
        assert "OK" in ret.output


def test_device_common_read_until_pattern():

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:

        global g_mock_read

        config = mockdevice.return_value
        dev = DeviceMock(config)

        # success: pattern found in output
        g_mock_read = b"PASS: all tests ok"
        ret = dev.read_until_pattern(b"PASS", 10)
        assert ret.status == CmdStatus.SUCCESS

        # fail_pattern detected → FAILED
        g_mock_read = b"FAIL: assertion error"
        ret = dev.read_until_pattern(b"PASS", 10, fail_pattern=b"FAIL")
        assert ret.status == CmdStatus.FAILED

        # timeout when neither pattern matches
        g_mock_read = b"still running..."
        ret = dev.read_until_pattern(b"PASS", 1)
        assert ret.status == CmdStatus.TIMEOUT

        # TypeError for non-bytes pattern
        with pytest.raises(TypeError):
            dev.read_until_pattern("PASS", 10)


def test_device_common_panic_char():

    with patch("ntfc.device.common.get_os") as mock_get_os:
        mock_get_os.return_value = SimpleNamespace(
            panic_char="X", crash_signatures={}
        )

        with patch("ntfc.envconfig.EnvConfig") as mockdevice:
            config = mockdevice.return_value

            dev = DeviceMock(config)
            assert dev.panic_char == "X"


def test_device_common_log_helpers():

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:
        config = mockdevice.return_value

        dev = DeviceMock(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            h1 = LogHandler(tmpdir, "batch1")
            dev.start_log_collect(h1)

            dev._log_device_event("event")
            dev._log_console_input(b"cmd\n")
            dev.log_event("public")

            dev._log_runtime_event("reboot")
            dev._mark_started()
            dev._log_runtime_event("poweroff")
            assert dev.reboot() is False
            assert dev.poweroff() is False

            dev.stop_log_collect()
            h1.close()

            device_path = os.path.join(
                tmpdir, "batch1" + LogHandler.DEVICE_SUFFIX
            )
            with open(device_path) as f:
                output = f.read()
            assert "event" in output
            assert "console_in" in output
            assert "public" in output
            assert "runtime=unknown" in output
            assert "poweroff runtime=" in output

            dev._log_device_event("buffered")
            dev._log_console_input(b"buffered-cmd")
            h2 = LogHandler(tmpdir, "batch2")
            dev.start_log_collect(h2)
            dev.stop_log_collect()
            h2.close()

            device_path = os.path.join(
                tmpdir, "batch2" + LogHandler.DEVICE_SUFFIX
            )
            with open(device_path) as f:
                output = f.read()
            assert "buffered" in output
            assert "buffered-cmd" in output


def test_pid_default_none():

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:
        config = mockdevice.return_value
        dev = DeviceMock(config)

        assert dev.pid is None


def test_output_tail_accumulates():

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:
        config = mockdevice.return_value
        dev = DeviceMock(config)

        dev._output_tail_append(b"hello ")
        dev._output_tail_append(b"world")
        assert dev.output_tail() == "hello world"


def test_output_tail_capped():

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:
        config = mockdevice.return_value
        dev = DeviceMock(config)

        dev._output_tail_append(b"x" * (4 * 1024 * 1024))
        dev._output_tail_append(b"tail-marker")
        tail = dev.output_tail()
        assert len(tail) <= 4 * 1024 * 1024
        assert tail.endswith("tail-marker")


def test_reset_output_tail_clears_buffer():

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:
        config = mockdevice.return_value
        dev = DeviceMock(config)

        dev._output_tail_append(b"stale crash markers")
        dev.reset_output_tail()

        assert dev.output_tail() == ""
        dev._output_tail_append(b"fresh")
        assert dev.output_tail() == "fresh"


def test_read_all_appends_chunks_to_output_tail(monkeypatch):

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:
        config = mockdevice.return_value
        dev = DeviceMock(config)

        chunks = [b"AAA", b"BBB"]

        def fake_read(_=0):
            return chunks.pop(0) if chunks else b""

        monkeypatch.setattr(dev, "_read", fake_read)
        dev._read_all(timeout=0.05)

        # per-chunk append, not cumulative re-append of growing output
        assert dev.output_tail() == "AAABBB"


# TODO: missing tests
