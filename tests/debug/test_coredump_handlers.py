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

import base64
import os
import struct
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from ntfc.debug.config import LocalFileConfig
from ntfc.debug.coredump.fastboot_handler import FastbootHandler
from ntfc.debug.coredump.gdb_handler import GdbHandler
from ntfc.debug.coredump.local_file_handler import LocalFileHandler
from ntfc.debug.coredump.syslog_handler import SyslogHandler
from ntfc.debug.coredump.ymodem_handler import YmodemHandler
from ntfc.device.common import CmdReturn, CmdStatus


class TestGdbHandler:
    def _make_handler(
        self, running: bool = True, corefile: "Path | None" = None
    ) -> GdbHandler:
        controller = MagicMock()
        controller.is_running.return_value = running
        controller.generate_coredump.return_value = corefile
        return GdbHandler(controller)

    def test_name(self) -> None:
        h = self._make_handler()
        assert h.name == "gdb"

    def test_priority(self) -> None:
        h = self._make_handler()
        assert h.priority == 10

    def test_is_available_when_running(self) -> None:
        h = self._make_handler(running=True)
        assert h.is_available() is True

    def test_is_available_when_stopped(self) -> None:
        h = self._make_handler(running=False)
        assert h.is_available() is False

    def test_collect_returns_true_when_controller_returns_path(
        self, tmp_path: "Path"
    ) -> None:
        h = self._make_handler(corefile=tmp_path / "core")
        assert h.collect(tmp_path, "prefix") is True

    def test_collect_returns_false_when_controller_returns_none(
        self, tmp_path: "Path"
    ) -> None:
        h = self._make_handler(corefile=None)
        assert h.collect(tmp_path, "prefix") is False

    def test_collect_passes_args_to_controller(self, tmp_path: "Path") -> None:
        controller = MagicMock()
        controller.generate_coredump.return_value = tmp_path / "x.core"
        h = GdbHandler(controller)
        h.collect(tmp_path, "myprefix")
        controller.generate_coredump.assert_called_once_with(
            tmp_path, "myprefix"
        )

    def test_collect_forces_panic_before_coredump(
        self, tmp_path: "Path"
    ) -> None:
        calls = []
        controller = MagicMock()
        controller.generate_coredump.side_effect = (
            lambda *a: calls.append("gcore") or tmp_path / "x.core"
        )
        panic = MagicMock(side_effect=lambda: calls.append("panic") or True)
        h = GdbHandler(controller, force_panic=panic)
        assert h.collect(tmp_path, "prefix") is True
        assert calls == ["panic", "gcore"]

    def test_collect_continues_when_panic_fails(
        self, tmp_path: "Path"
    ) -> None:
        controller = MagicMock()
        controller.generate_coredump.return_value = tmp_path / "x.core"
        panic = MagicMock(return_value=False)
        h = GdbHandler(controller, force_panic=panic)
        assert h.collect(tmp_path, "prefix") is True
        controller.generate_coredump.assert_called_once()

    def test_collect_skips_panic_when_not_configured(
        self, tmp_path: "Path"
    ) -> None:
        h = self._make_handler(corefile=tmp_path / "x.core")
        assert h.collect(tmp_path, "prefix") is True

    def test_enabled_by_default(self) -> None:
        h = self._make_handler()
        assert h.is_enabled() is True

    def test_disable_then_enable(self) -> None:
        h = self._make_handler()
        h.disable()
        assert h.is_enabled() is False
        h.enable()
        assert h.is_enabled() is True

    def test_collect_waits_for_auto_dump_on_crash(
        self, tmp_path: "Path"
    ) -> None:
        src = tmp_path / "crash.123.core"
        src.write_bytes(b"\x7fELF")
        controller = MagicMock()
        controller.wait_corefile.return_value = src
        h = GdbHandler(controller, crash_check=lambda: True, auto_dump=True)
        out = tmp_path / "out"
        out.mkdir()
        assert h.collect(out, "test_x") is True
        controller.wait_corefile.assert_called_once_with(
            timeout=GdbHandler.AUTO_DUMP_TIMEOUT
        )
        controller.generate_coredump.assert_not_called()
        assert (out / "test_x.core").read_bytes() == b"\x7fELF"

    def test_collect_auto_dump_timeout_returns_false(
        self, tmp_path: "Path"
    ) -> None:
        controller = MagicMock()
        controller.wait_corefile.return_value = None
        h = GdbHandler(controller, crash_check=lambda: True, auto_dump=True)
        assert h.collect(tmp_path, "t") is False
        controller.generate_coredump.assert_not_called()

    def test_collect_pull_path_when_not_crashed(
        self, tmp_path: "Path"
    ) -> None:
        controller = MagicMock()
        controller.generate_coredump.return_value = tmp_path / "t.core"
        h = GdbHandler(controller, crash_check=lambda: False, auto_dump=True)
        assert h.collect(tmp_path, "t") is True
        controller.wait_corefile.assert_not_called()

    def test_collect_pull_path_without_auto_dump(
        self, tmp_path: "Path"
    ) -> None:
        controller = MagicMock()
        controller.generate_coredump.return_value = tmp_path / "t.core"
        h = GdbHandler(controller, crash_check=lambda: True, auto_dump=False)
        assert h.collect(tmp_path, "t") is True
        controller.wait_corefile.assert_not_called()


class TestFastbootHandler:
    def _make_handler(
        self,
        connected: bool = True,
        memdump_result: "Path | None" = None,
        mem_addr: str = "0x40000000",
        mem_size: str = "0x08000000",
    ) -> FastbootHandler:
        controller = MagicMock()
        controller.is_connected.return_value = connected
        controller.memdump.return_value = memdump_result
        return FastbootHandler(controller, mem_addr, mem_size)

    def test_name(self) -> None:
        assert self._make_handler().name == "fastboot"

    def test_priority(self) -> None:
        assert self._make_handler().priority == 20

    def test_is_available_when_connected(self) -> None:
        assert self._make_handler(connected=True).is_available() is True

    def test_is_available_when_disconnected(self) -> None:
        assert self._make_handler(connected=False).is_available() is False

    def test_collect_returns_true_when_memdump_returns_path(
        self, tmp_path: "Path"
    ) -> None:
        h = self._make_handler(memdump_result=tmp_path / "core.bin")
        assert h.collect(tmp_path, "prefix") is True

    def test_collect_returns_false_when_memdump_returns_none(
        self, tmp_path: "Path"
    ) -> None:
        h = self._make_handler(memdump_result=None)
        assert h.collect(tmp_path, "prefix") is False

    def test_collect_passes_addr_size_and_path_to_controller(
        self, tmp_path: "Path"
    ) -> None:
        controller = MagicMock()
        controller.memdump.return_value = tmp_path / "myprefix.bin"
        h = FastbootHandler(controller, "0x20000000", "0x04000000")
        h.collect(tmp_path, "myprefix")
        controller.memdump.assert_called_once_with(
            "0x20000000",
            "0x04000000",
            tmp_path / "myprefix.bin",
        )

    def test_enabled_by_default(self) -> None:
        assert self._make_handler().is_enabled() is True

    def test_disable_then_enable(self) -> None:
        h = self._make_handler()
        h.disable()
        assert h.is_enabled() is False
        h.enable()
        assert h.is_enabled() is True


def _make_device(
    output: str = "", status: CmdStatus = CmdStatus.SUCCESS
) -> MagicMock:
    d = MagicMock()
    d.send_cmd_read_until_pattern.return_value = CmdReturn(
        status=status, output=output
    )
    return d


class TestYmodemHandler:
    def _make_handler(
        self,
        ready: bool = True,
        ls_output: str = "app.core\n",
        ls_status: CmdStatus = CmdStatus.SUCCESS,
        download_result: bool = True,
    ) -> YmodemHandler:
        controller = MagicMock()
        controller.is_ready.return_value = ready
        controller.download.return_value = download_result
        device = _make_device(output=ls_output, status=ls_status)
        return YmodemHandler(controller, device)

    def test_name(self) -> None:
        assert self._make_handler().name == "ymodem"

    def test_priority(self) -> None:
        assert self._make_handler().priority == 30

    def test_is_available_when_ready(self) -> None:
        assert self._make_handler(ready=True).is_available() is True

    def test_is_available_when_not_ready(self) -> None:
        assert self._make_handler(ready=False).is_available() is False

    def test_collect_returns_true_on_success(self, tmp_path: "Path") -> None:
        assert self._make_handler().collect(tmp_path, "test") is True

    def test_collect_returns_false_when_ls_finds_no_core(
        self, tmp_path: "Path"
    ) -> None:
        h = self._make_handler(ls_output="no files here\n")
        assert h.collect(tmp_path, "test") is False

    def test_collect_returns_false_when_ls_times_out(
        self, tmp_path: "Path"
    ) -> None:
        h = self._make_handler(ls_status=CmdStatus.TIMEOUT)
        assert h.collect(tmp_path, "test") is False

    def test_collect_returns_false_when_download_fails(
        self, tmp_path: "Path"
    ) -> None:
        assert (
            self._make_handler(download_result=False).collect(tmp_path, "t")
            is False
        )

    def test_collect_does_not_download_when_find_fails(
        self, tmp_path: "Path"
    ) -> None:
        controller = MagicMock()
        controller.is_ready.return_value = True
        controller.download.return_value = True
        device = _make_device(output="no files here\n")
        h = YmodemHandler(controller, device)
        h.collect(tmp_path, "t")
        controller.download.assert_not_called()
        device.stop.assert_not_called()

    def test_collect_releases_port_during_download(
        self, tmp_path: "Path"
    ) -> None:
        """Device is stopped before download and restarted after."""
        calls = []
        controller = MagicMock()
        controller.is_ready.return_value = True
        controller.download.side_effect = (
            lambda *a: calls.append("download") or True
        )
        device = _make_device(output="app.core\n")
        device.stop.side_effect = lambda: calls.append("stop")
        device.start.side_effect = lambda: calls.append("start")
        h = YmodemHandler(controller, device)
        assert h.collect(tmp_path, "t") is True
        assert calls == ["stop", "download", "start"]

    def test_collect_restarts_device_when_download_raises(
        self, tmp_path: "Path"
    ) -> None:
        controller = MagicMock()
        controller.is_ready.return_value = True
        controller.download.side_effect = RuntimeError("boom")
        device = _make_device(output="app.core\n")
        h = YmodemHandler(controller, device)
        with pytest.raises(RuntimeError):
            h.collect(tmp_path, "t")
        device.start.assert_called_once()

    def test_enabled_by_default(self) -> None:
        assert self._make_handler().is_enabled() is True

    def test_disable_then_enable(self) -> None:
        h = self._make_handler()
        h.disable()
        assert h.is_enabled() is False
        h.enable()
        assert h.is_enabled() is True


class TestLocalFileHandler:
    def _make(self, core_dir: "Path") -> LocalFileHandler:
        return LocalFileHandler(LocalFileConfig({"core_dir": str(core_dir)}))

    def test_name_and_priority(self, tmp_path: "Path") -> None:
        h = self._make(tmp_path)
        assert h.name == "local_file"
        assert h.priority == 15

    def test_unavailable_when_dir_missing(self, tmp_path: "Path") -> None:
        assert self._make(tmp_path / "nope").is_available() is False

    def test_collects_newest_matching_file(self, tmp_path: "Path") -> None:
        src = tmp_path / "cores"
        src.mkdir()
        old = src / "old.core"
        old.write_bytes(b"OLD1")
        new = src / "new.core"
        new.write_bytes(b"NEW1")
        os.utime(old, (1, 1))
        out = tmp_path / "out"
        h = self._make(src)
        assert h.collect(out, "test_x") is True
        assert (out / "test_x.core").read_bytes() == b"NEW1"
        assert not new.exists()

    def test_does_not_recollect_consumed_file(self, tmp_path: "Path") -> None:
        src = tmp_path / "cores"
        src.mkdir()
        (src / "a.core").write_bytes(b"AAAA")
        out = tmp_path / "out"
        h = self._make(src)
        assert h.collect(out, "one") is True
        assert h.collect(out, "two") is False

    def test_ignores_empty_files(self, tmp_path: "Path") -> None:
        src = tmp_path / "cores"
        src.mkdir()
        (src / "empty.core").write_bytes(b"")
        h = self._make(src)
        assert h.collect(tmp_path / "out", "t") is False

    def test_respects_pattern(self, tmp_path: "Path") -> None:
        src = tmp_path / "cores"
        src.mkdir()
        (src / "x.dump").write_bytes(b"DUMP")
        h = LocalFileHandler(
            LocalFileConfig({"core_dir": str(src), "pattern": "*.dump"})
        )
        assert h.collect(tmp_path / "out", "t") is True


class TestYmodemHandlerParseCorefile:
    def test_returns_name_for_unformatted_file(self) -> None:
        assert YmodemHandler._parse_corefile("app.core\n") == "app.core"

    def test_skips_already_stamped_files(self) -> None:
        out = "crash.2025.01.01_12.00.00.core\n"
        assert YmodemHandler._parse_corefile(out) is None

    def test_returns_first_unformatted_when_mixed(self) -> None:
        out = "crash.2025.01.01_12.00.00.core\nfresh.core\n"
        assert YmodemHandler._parse_corefile(out) == "fresh.core"

    def test_returns_none_when_no_core_files(self) -> None:
        assert YmodemHandler._parse_corefile("no files here\n") is None

    def test_returns_none_on_empty_output(self) -> None:
        assert YmodemHandler._parse_corefile("") is None


class TestYmodemHandlerFindCoredump:
    def test_returns_renamed_name_on_success(self) -> None:
        device = _make_device(output="app.core\n")
        h = YmodemHandler(MagicMock(), device)
        result = h._find_coredump("test")
        assert result is not None
        assert result.startswith("test.")
        assert result.endswith(".core")

    def test_returns_none_when_ls_times_out(self) -> None:
        device = _make_device(output="", status=CmdStatus.TIMEOUT)
        h = YmodemHandler(MagicMock(), device)
        assert h._find_coredump("test") is None

    def test_returns_none_when_all_files_stamped(self) -> None:
        device = _make_device(output="crash.2025.01.01_00.00.00.core\n")
        h = YmodemHandler(MagicMock(), device)
        assert h._find_coredump("test") is None

    def test_sends_rename_command_on_success(self) -> None:
        device = _make_device(output="app.core\n")
        h = YmodemHandler(MagicMock(), device)
        h._find_coredump("myprefix")
        assert device.send_cmd_read_until_pattern.call_count == 2
        mv_call = device.send_cmd_read_until_pattern.call_args_list[1]
        assert b"mv" in mv_call[0][0]
        assert b"myprefix" in mv_call[0][0]


def _syslog_output(payload_b64: str) -> str:
    lines = ["[    1.0] Start coredump\n"]
    for i in range(0, len(payload_b64), 8):
        lines.append(f"[    1.1] {payload_b64[i:i + 8]}\n")
    lines.append("[    1.2] Finish coredump\n")
    return "boot noise\n" + "".join(lines) + "after noise\n"


def _raw_block(data: bytes) -> bytes:
    return b"ZV\x00" + struct.pack(">H", len(data)) + data


class TestSyslogHandler:
    def _make(self, output: str) -> SyslogHandler:
        device = MagicMock()
        device.output_tail.return_value = output
        return SyslogHandler(device)

    def test_name_and_priority(self) -> None:
        h = self._make("")
        assert h.name == "syslog"
        assert h.priority == 25
        assert h.is_available() is True

    def test_collect_decodes_raw_blocks(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        monkeypatch.setattr(
            "ntfc.debug.coredump.syslog_handler.lzf", MagicMock()
        )
        payload = base64.b64encode(_raw_block(b"\x7fELF-core")).decode()
        h = self._make(_syslog_output(payload))
        assert h.collect(tmp_path, "t") is True
        assert (tmp_path / "t.core").read_bytes() == b"\x7fELF-core"
        h._device.reset_output_tail.assert_called_once()

    def test_collect_clears_tail_even_when_no_markers_found(
        self, tmp_path: "Path"
    ) -> None:
        h = self._make("no markers here")
        assert h.collect(tmp_path, "t") is False
        h._device.reset_output_tail.assert_called_once()

    def test_collect_decompresses_lzf_blocks(self, tmp_path: "Path") -> None:
        """Round-trip a real liblzf-compressed block through the actual
        ``lzf`` cffi package (not a mock) -- a mocked ``.decompress()``
        previously hid an API mismatch with the real package, which has
        no such module-level function."""
        lzf = pytest.importorskip("lzf")
        plaintext = b"\x7fELF-expanded" * 200
        dest = bytearray(lzf.LZF_MAX_COMPRESSED_SIZE(len(plaintext)))
        compressed_len = lzf.lib.lzf_compress(
            lzf.ffi.from_buffer(plaintext),
            len(plaintext),
            lzf.ffi.from_buffer(dest),
            len(dest),
        )
        assert compressed_len > 0
        compressed = bytes(dest[:compressed_len])

        block = (
            b"ZV\x01"
            + struct.pack(">H", compressed_len)
            + struct.pack(">H", len(plaintext))
            + compressed
        )
        payload = base64.b64encode(block).decode()
        h = self._make(_syslog_output(payload))
        assert h.collect(tmp_path, "t") is True
        assert (tmp_path / "t.core").read_bytes() == plaintext

    def test_collect_fails_when_lzf_block_decompression_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        fake_lzf = MagicMock()
        fake_lzf.ffi.new.return_value = bytearray(13)
        fake_lzf.lib.lzf_decompress.return_value = 0
        monkeypatch.setattr("ntfc.debug.coredump.syslog_handler.lzf", fake_lzf)
        block = (
            b"ZV\x01" + struct.pack(">H", 4) + struct.pack(">H", 13) + b"COMP"
        )
        payload = base64.b64encode(block).decode()
        h = self._make(_syslog_output(payload))
        assert h.collect(tmp_path, "t") is False
        fake_lzf.lib.lzf_decompress.assert_called_once_with(
            b"COMP", 4, fake_lzf.ffi.new.return_value, 13
        )

    def test_collect_fails_without_markers(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        monkeypatch.setattr(
            "ntfc.debug.coredump.syslog_handler.lzf", MagicMock()
        )
        h = self._make("no coredump here\n")
        assert h.collect(tmp_path, "t") is False

    def test_collect_fails_on_bad_base64(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        monkeypatch.setattr(
            "ntfc.debug.coredump.syslog_handler.lzf", MagicMock()
        )
        h = self._make(_syslog_output("!!!not-base64!!!"))
        assert h.collect(tmp_path, "t") is False

    def test_collect_fails_on_bad_magic(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        monkeypatch.setattr(
            "ntfc.debug.coredump.syslog_handler.lzf", MagicMock()
        )
        payload = base64.b64encode(b"XX\x00garbage").decode()
        h = self._make(_syslog_output(payload))
        assert h.collect(tmp_path, "t") is False

    def test_collect_fails_on_truncated_clen(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        monkeypatch.setattr(
            "ntfc.debug.coredump.syslog_handler.lzf", MagicMock()
        )
        payload = base64.b64encode(b"ZV\x00\x00").decode()
        h = self._make(_syslog_output(payload))
        assert h.collect(tmp_path, "t") is False

    def test_collect_fails_on_truncated_ulen(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        monkeypatch.setattr(
            "ntfc.debug.coredump.syslog_handler.lzf", MagicMock()
        )
        block = b"ZV\x01" + struct.pack(">H", 4) + b"\x00"
        payload = base64.b64encode(block).decode()
        h = self._make(_syslog_output(payload))
        assert h.collect(tmp_path, "t") is False

    def test_collect_fails_on_unknown_block_type(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        monkeypatch.setattr(
            "ntfc.debug.coredump.syslog_handler.lzf", MagicMock()
        )
        block = b"ZV\x02" + struct.pack(">H", 0)
        payload = base64.b64encode(block).decode()
        h = self._make(_syslog_output(payload))
        assert h.collect(tmp_path, "t") is False

    def test_collect_handles_payload_line_without_prefix(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        monkeypatch.setattr(
            "ntfc.debug.coredump.syslog_handler.lzf", MagicMock()
        )
        payload = base64.b64encode(_raw_block(b"\x7fELF-core")).decode()
        output = "Start coredump\n" + payload + "\nFinish coredump\n"
        h = self._make(output)
        assert h.collect(tmp_path, "t") is True
        assert (tmp_path / "t.core").read_bytes() == b"\x7fELF-core"

    def test_collect_uses_last_complete_pair_ignoring_trailing_start(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        monkeypatch.setattr(
            "ntfc.debug.coredump.syslog_handler.lzf", MagicMock()
        )
        payload = base64.b64encode(_raw_block(b"\x7fELF-core")).decode()
        output = (
            _syslog_output(payload)
            + "[    2.0] Start coredump\n"
            + "[    2.1] AAAA\n"
        )
        h = self._make(output)
        assert h.collect(tmp_path, "t") is True
        assert (tmp_path / "t.core").read_bytes() == b"\x7fELF-core"

    def test_collect_fails_when_only_unterminated_start(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: "Path"
    ) -> None:
        monkeypatch.setattr(
            "ntfc.debug.coredump.syslog_handler.lzf", MagicMock()
        )
        output = "[    1.0] Start coredump\n[    1.1] AAAA\n"
        h = self._make(output)
        assert h.collect(tmp_path, "t") is False
