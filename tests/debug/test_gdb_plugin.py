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

"""Tests for the NTFC in-GDB plugin scripts (with a fake gdb module)."""

import builtins
import importlib
import sys
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType


@pytest.fixture
def autobp(
    fake_gdb: "ModuleType",
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: "Path",
) -> "ModuleType":
    """Import a fresh autobp module against the fake gdb module."""
    mod = importlib.import_module("ntfc.debug.gdb.plugin.autobp")
    monkeypatch.setattr(mod, "NTFC_DIR_FILE", str(tmp_path / ".ntfc_dir"))
    return mod


def _command(fake_gdb: "ModuleType", name: str) -> Any:
    """Return the registered command instance by name."""
    return dict(fake_gdb.Command.registered)[name]


class TestResultCheck:
    def test_success_printed(
        self, autobp: "ModuleType", capsys: pytest.CaptureFixture[str]
    ) -> None:
        wrapped = autobp._result_check(lambda self, a, tty: True)
        assert wrapped(object(), "arg", False) is True
        assert "Success: object arg" in capsys.readouterr().out

    def test_failure_printed(
        self, autobp: "ModuleType", capsys: pytest.CaptureFixture[str]
    ) -> None:
        wrapped = autobp._result_check(lambda self, a, tty: False)
        assert wrapped(object(), "arg", False) is False
        assert "Failed: object arg" in capsys.readouterr().out

    def test_no_args_formatting(
        self, autobp: "ModuleType", capsys: pytest.CaptureFixture[str]
    ) -> None:
        wrapped = autobp._result_check(lambda self: True)
        assert wrapped(object()) is True
        assert "Success: object" in capsys.readouterr().out


class TestOutputDirHelpers:
    def test_get_from_global(
        self, autobp: "ModuleType", monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(autobp, "_output_dir", "/some/dir")
        assert autobp._output_dir_get() == "/some/dir"

    def test_get_from_backup_file(
        self, autobp: "ModuleType", tmp_path: "Path"
    ) -> None:
        backup = tmp_path / ".ntfc_dir"
        backup.write_text("/from/file")
        assert autobp._output_dir_get() == "/from/file"

    def test_get_from_empty_backup_file(
        self, autobp: "ModuleType", tmp_path: "Path"
    ) -> None:
        backup = tmp_path / ".ntfc_dir"
        backup.write_text("")
        assert autobp._output_dir_get() is None

    def test_get_backup_file_read_error(
        self,
        autobp: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: "Path",
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # A directory triggers OSError on open()
        (tmp_path / ".ntfc_dir").mkdir()
        assert autobp._output_dir_get() is None
        assert "Could not read backup file" in capsys.readouterr().out

    def test_get_unset(self, autobp: "ModuleType") -> None:
        assert autobp._output_dir_get() is None

    def test_ensure_existing_dir(
        self, autobp: "ModuleType", tmp_path: "Path"
    ) -> None:
        assert autobp._output_dir_ensure(str(tmp_path)) is True

    def test_ensure_creates_dir(
        self, autobp: "ModuleType", tmp_path: "Path"
    ) -> None:
        target = tmp_path / "new" / "dir"
        assert autobp._output_dir_ensure(str(target)) is True
        assert target.is_dir()

    def test_ensure_failure(
        self, autobp: "ModuleType", tmp_path: "Path"
    ) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("x")
        assert autobp._output_dir_ensure(str(blocker / "sub")) is False


class TestAutoBp:
    def test_breakpoint_type(self, autobp: "ModuleType") -> None:
        bp = autobp.AutoBp("main", ["bt"], bp_type="bp")
        assert bp.bp_type == 0

    def test_watchpoint_type(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        bp = autobp.AutoBp("var", ["bt"], bp_type="wp")
        assert bp.bp_type == fake_gdb.BP_WATCHPOINT

    def test_crash_coredump_registration(self, autobp: "ModuleType") -> None:
        bp = autobp.AutoBp("dump_mini_info", ["ntfcautogcore -d /x gcore"])
        assert (
            autobp.AutoBp._crash_coredump_breakpoints["dump_mini_info"] is bp
        )

    def test_no_registration_without_autogcore(
        self, autobp: "ModuleType"
    ) -> None:
        autobp.AutoBp("dump_mini_info", ["bt"])
        assert autobp.AutoBp._crash_coredump_breakpoints == {}

    def test_no_registration_for_other_spec(
        self, autobp: "ModuleType"
    ) -> None:
        autobp.AutoBp("main", ["ntfcautogcore -d /x gcore"])
        assert autobp.AutoBp._crash_coredump_breakpoints == {}

    def test_stop_executes_commands(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        bp = autobp.AutoBp("main", ["bt", "info registers"])
        assert bp.stop() is True
        assert "bt" in fake_gdb.executed
        assert "info registers" in fake_gdb.executed
        assert bp in autobp.AutoBp._pending_delete

    def test_stop_swallows_gdb_error(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def fail(cmd: str, to_string: bool = False) -> str:
            raise fake_gdb.error("boom")

        monkeypatch.setattr(fake_gdb, "execute", fail)
        bp = autobp.AutoBp("main", ["bt"])
        assert bp.stop() is True
        assert "Command failed" in capsys.readouterr().out

    def test_stop_deletes_crash_siblings(
        self, autobp: "ModuleType", capsys: pytest.CaptureFixture[str]
    ) -> None:
        gcore = ["ntfcautogcore -d /x gcore"]
        bp_a = autobp.AutoBp("dump_mini_info", gcore)
        bp_b = autobp.AutoBp("dump_core_info", gcore)
        assert bp_a.stop() is True
        assert bp_a in autobp.AutoBp._pending_delete
        assert bp_b in autobp.AutoBp._pending_delete
        assert autobp.AutoBp._crash_coredump_breakpoints == {}
        assert "deleting sibling" in capsys.readouterr().out.lower()


class TestNtfcAutoBpCommand:
    def test_registered(self, autobp: "ModuleType", fake_gdb: "ModuleType"):
        assert "ntfcautobp" in dict(fake_gdb.Command.registered)

    def test_too_few_args(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcautobp")
        assert cmd.invoke("bp main", False) is False

    def test_invalid_bp_type(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcautobp")
        assert cmd.invoke("xx main bt", False) is False

    def test_valid_breakpoint(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcautobp")
        assert cmd.invoke("bp main bt;continue", False) is True
        bp = fake_gdb.Breakpoint.instances[-1]
        assert bp.spec == "main"
        assert bp._cmds == ["bt", "continue"]

    def test_valid_watchpoint(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcautobp")
        assert cmd.invoke("wp counter bt", False) is True
        bp = fake_gdb.Breakpoint.instances[-1]
        assert bp.bp_type == fake_gdb.BP_WATCHPOINT

    def test_invalid_breakpoint(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(fake_gdb.Breakpoint, "valid", False)
        cmd = _command(fake_gdb, "ntfcautobp")
        assert cmd.invoke("bp main bt", False) is False


class TestNtfcSetOutDirCommand:
    def test_usage_on_wrong_argc(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        cmd = _command(fake_gdb, "ntfcsetoutdir")
        cmd.invoke("a b", False)
        assert "Usage:" in capsys.readouterr().out

    def test_sets_dir_and_backup_file(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        tmp_path: "Path",
    ) -> None:
        out = tmp_path / "results"
        cmd = _command(fake_gdb, "ntfcsetoutdir")
        cmd.invoke(str(out), False)
        assert autobp._output_dir == str(out)
        assert out.is_dir()
        backup = tmp_path / ".ntfc_dir"
        assert backup.read_text() == str(out)

    def test_dir_create_failure(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        tmp_path: "Path",
    ) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("x")
        cmd = _command(fake_gdb, "ntfcsetoutdir")
        cmd.invoke(str(blocker / "sub"), False)
        assert autobp._output_dir is None

    def test_backup_file_write_failure(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: "Path",
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            autobp, "NTFC_DIR_FILE", str(tmp_path / "no" / "dir" / "f")
        )
        cmd = _command(fake_gdb, "ntfcsetoutdir")
        cmd.invoke(str(tmp_path), False)
        assert autobp._output_dir == str(tmp_path)
        assert "Could not write to backup file" in capsys.readouterr().out


class TestNtfcAutoGcoreCommand:
    def _gcore_creates(
        self,
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        content: bytes = b"\x7fELF-core",
    ) -> None:
        """Make fake gcore commands create the target file.

        Only ``gcore <path>`` commands reach the fake in these tests, so
        the last token is always the corefile path.
        """
        import pathlib

        def execute(cmd: str, to_string: bool = False) -> str:
            fake_gdb.executed.append(cmd)
            pathlib.Path(cmd.split()[-1]).write_bytes(content)
            return ""

        monkeypatch.setattr(fake_gdb, "execute", execute)

    def test_no_args(self, autobp: "ModuleType", fake_gdb: "ModuleType"):
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd.invoke("", False) is False

    def test_wrong_first_flag(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd.invoke("-x /tmp gcore", False) is False

    def test_dynamic_dir_not_set(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd.invoke("-d $RESULT_DIR gcore", False) is False

    def test_dynamic_dir_from_backup_file(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: "Path",
    ) -> None:
        (tmp_path / ".ntfc_dir").write_text(str(tmp_path))
        self._gcore_creates(fake_gdb, monkeypatch)
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd.invoke("-d $RESULT_DIR gcore", False) is True
        assert list(tmp_path.glob("*.core"))

    def test_name_flag_missing_value(
        self, autobp: "ModuleType", fake_gdb: "ModuleType", tmp_path: "Path"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd.invoke(f"-d {tmp_path} -n", False) is False

    def test_name_flag_used_in_filename(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: "Path",
    ) -> None:
        self._gcore_creates(fake_gdb, monkeypatch)
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd.invoke(f"-d {tmp_path} -n myname gcore", False) is True
        cores = list(tmp_path.glob("myname.*.core"))
        assert len(cores) == 1

    def test_dir_create_failure(
        self, autobp: "ModuleType", fake_gdb: "ModuleType", tmp_path: "Path"
    ) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("x")
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd.invoke(f"-d {blocker / 'sub'} gcore", False) is False

    def test_gcore_command_fails(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: "Path",
    ) -> None:
        def fail(cmd: str, to_string: bool = False) -> str:
            raise fake_gdb.error("no such command")

        monkeypatch.setattr(fake_gdb, "execute", fail)
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd.invoke(f"-d {tmp_path} gcore", False) is False

    def test_corefile_not_created(
        self, autobp: "ModuleType", fake_gdb: "ModuleType", tmp_path: "Path"
    ) -> None:
        # default fake execute does not create any file
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd.invoke(f"-d {tmp_path} gcore", False) is False

    def test_corefile_invalid_header(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: "Path",
    ) -> None:
        self._gcore_creates(fake_gdb, monkeypatch, content=b"XXXX")
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd.invoke(f"-d {tmp_path} gcore", False) is False

    def test_corefile_read_error(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: "Path",
    ) -> None:
        corefile = tmp_path / "x.core"
        corefile.write_bytes(b"\x7fELF")
        real_open = builtins.open

        def bad_open(file: Any, *args: Any, **kwargs: Any) -> Any:
            if str(file) == str(corefile):
                raise OSError("boom")
            return real_open(file, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", bad_open)
        cmd = _command(fake_gdb, "ntfcautogcore")
        assert cmd._verify_coredump(str(corefile)) is False
        # exercise the pass-through branch of bad_open
        with bad_open(tmp_path / "other.txt", "w") as f:
            f.write("ok")


class TestNtfcAutoMmleakCommand:
    def test_no_args(self, autobp: "ModuleType", fake_gdb: "ModuleType"):
        cmd = _command(fake_gdb, "ntfcmmleak")
        assert cmd.invoke("", False) is False

    def test_wrong_first_flag(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcmmleak")
        assert cmd.invoke("-x /tmp gcore", False) is False

    def test_dynamic_dir_not_set(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcmmleak")
        assert cmd.invoke("-d $RESULT_DIR gcore", False) is False

    def test_dynamic_dir_from_global(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: "Path",
    ) -> None:
        monkeypatch.setattr(autobp, "_output_dir", str(tmp_path))
        cmd = _command(fake_gdb, "ntfcmmleak")
        assert cmd.invoke("-d $RESULT_DIR gcore", False) is True

    def test_no_leak_no_dump(
        self, autobp: "ModuleType", fake_gdb: "ModuleType", tmp_path: "Path"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcmmleak")
        assert cmd.invoke(f"-d {tmp_path} gcore", False) is True
        assert not (tmp_path / "nuttx.mmleak").exists()

    def test_zero_leaked_blocks_no_dump(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: "Path",
    ) -> None:
        def execute(cmd: str, to_string: bool = False) -> str:
            fake_gdb.executed.append(cmd)
            return "Leaked 0 blks, 0 bytes"

        monkeypatch.setattr(fake_gdb, "execute", execute)
        cmd = _command(fake_gdb, "ntfcmmleak")
        assert cmd.invoke(f"-d {tmp_path} gcore", False) is True
        assert not (tmp_path / "nuttx.mmleak").exists()

    def test_leak_writes_report_and_dumps(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: "Path",
    ) -> None:
        def execute(cmd: str, to_string: bool = False) -> str:
            fake_gdb.executed.append(cmd)
            if cmd == "mm leak":
                return "Leaked 3 blks, 24 bytes"
            return ""

        monkeypatch.setattr(fake_gdb, "execute", execute)
        cmd = _command(fake_gdb, "ntfcmmleak")
        assert cmd.invoke(f"-d {tmp_path} gcore", False) is True
        report = tmp_path / "nuttx.mmleak"
        assert report.read_text() == "Leaked 3 blks, 24 bytes"
        gcores = [c for c in fake_gdb.executed if c.startswith("gcore ")]
        assert len(gcores) == 1
        assert ".core" in gcores[0]


class TestNtfcAutoPoweroffCheckCommand:
    def test_prints_backtrace(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        cmd = _command(fake_gdb, "ntfcautopoweroffcheck")
        assert cmd.invoke("", False) is True
        assert "bt" in fake_gdb.executed


class TestEventHandlers:
    def test_module_connects_events(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        assert autobp.gdb_autobp_stop_event in fake_gdb.events.stop.callbacks
        assert (
            autobp.gdb_process_exited_event in fake_gdb.events.exited.callbacks
        )

    def test_stop_event_deletes_pending_and_continues(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        bp = autobp.AutoBp("main", ["bt"])
        autobp.AutoBp._pending_delete.add(bp)
        autobp.gdb_autobp_stop_event(fake_gdb.BreakpointEvent())
        assert bp.deleted is True
        assert autobp.AutoBp._pending_delete == set()
        assert "continue" in fake_gdb.executed

    def test_stop_event_delete_failure(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bp = autobp.AutoBp("main", ["bt"])
        autobp.AutoBp._pending_delete.add(bp)
        monkeypatch.setattr(
            fake_gdb.Breakpoint, "delete_error", fake_gdb.error("x")
        )
        autobp.gdb_autobp_stop_event(fake_gdb.BreakpointEvent())
        assert "Failed to delete breakpoint" in capsys.readouterr().out
        assert bp in autobp.AutoBp._pending_delete

    def test_stop_event_no_pending(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        autobp.gdb_autobp_stop_event(fake_gdb.BreakpointEvent())
        assert "continue" in fake_gdb.executed

    def test_stop_event_continues_on_autobp_breakpoint(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        bp = autobp.AutoBp("main", ["bt"])
        event = fake_gdb.BreakpointEvent(breakpoints=(bp,))
        autobp.gdb_autobp_stop_event(event)
        assert "continue" in fake_gdb.executed

    def test_stop_event_does_not_resume_user_breakpoint(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        user_bp = fake_gdb.Breakpoint("my_function")
        pending = autobp.AutoBp("main", ["bt"])
        autobp.AutoBp._pending_delete.add(pending)
        event = fake_gdb.BreakpointEvent(breakpoints=(user_bp,))
        autobp.gdb_autobp_stop_event(event)
        assert "continue" not in fake_gdb.executed
        assert pending.deleted is False
        assert "not resuming" in capsys.readouterr().out

    def test_stop_event_mixed_breakpoints_not_resumed(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        user_bp = fake_gdb.Breakpoint("my_function")
        auto_bp = autobp.AutoBp("main", ["bt"])
        event = fake_gdb.BreakpointEvent(breakpoints=(user_bp, auto_bp))
        autobp.gdb_autobp_stop_event(event)
        assert "continue" not in fake_gdb.executed

    def test_stop_event_sigint(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        autobp.gdb_autobp_stop_event(fake_gdb.SignalEvent("SIGINT"))
        assert "SIGINT" in capsys.readouterr().out

    def test_stop_event_sigterm_quits(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        autobp.gdb_autobp_stop_event(fake_gdb.SignalEvent("SIGTERM"))
        assert "q" in fake_gdb.executed

    def test_stop_event_unexpected_signal(
        self,
        autobp: "ModuleType",
        fake_gdb: "ModuleType",
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        autobp.gdb_autobp_stop_event(fake_gdb.SignalEvent("SIGUSR1"))
        assert "Unexpected Signal" in capsys.readouterr().out

    def test_stop_event_other_event_ignored(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        autobp.gdb_autobp_stop_event(object())
        assert fake_gdb.executed == []

    def test_exited_event_quits(
        self, autobp: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        autobp.gdb_process_exited_event(object())
        assert "q" in fake_gdb.executed


class TestGdbPrefix:
    @pytest.fixture
    def gdbprefix(self, fake_gdb: "ModuleType") -> "ModuleType":
        return importlib.import_module("ntfc.debug.gdb.plugin.gdbprefix")

    def test_registered(
        self, gdbprefix: "ModuleType", fake_gdb: "ModuleType"
    ) -> None:
        assert "ntfcgdbprefix" in dict(fake_gdb.Command.registered)

    def test_successful_command(
        self,
        gdbprefix: "ModuleType",
        fake_gdb: "ModuleType",
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        cmd = _command(fake_gdb, "ntfcgdbprefix")
        cmd.invoke("info registers", False)
        assert "info registers" in fake_gdb.executed
        assert "run successful" in capsys.readouterr().out

    def test_failed_command_quits_gdb(
        self,
        gdbprefix: "ModuleType",
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def execute(cmd: str, to_string: bool = False) -> str:
            fake_gdb.executed.append(cmd)
            if cmd != "q":
                raise fake_gdb.error("bad command")
            return ""

        monkeypatch.setattr(fake_gdb, "execute", execute)
        cmd = _command(fake_gdb, "ntfcgdbprefix")
        cmd.invoke("bogus", False)
        assert "run failed" in capsys.readouterr().out
        assert "q" in fake_gdb.executed


class TestInitLoader:
    def test_load_imports_plugin_modules(
        self,
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(sys, "path", list(sys.path))
        init = importlib.import_module("ntfc.debug.gdb.plugin.init")
        init.load()
        out = capsys.readouterr().out
        assert "import autobp" in out
        assert "import gdbprefix" in out
        assert "NTFC GDB Plugin loaded Successfully" in out
        assert "ntfcautobp" in dict(fake_gdb.Command.registered)
        # Second call: plugin dir is already in sys.path
        init.load()

    def test_load_reports_import_errors(
        self,
        fake_gdb: "ModuleType",
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(sys, "path", list(sys.path))
        init = importlib.import_module("ntfc.debug.gdb.plugin.init")

        def fail(name: str) -> "ModuleType":
            raise ImportError(f"broken {name}")

        monkeypatch.setattr(init.importlib, "import_module", fail)
        init.load()
        out = capsys.readouterr().out
        assert "ImportError" in out
        assert "NTFC GDB Plugin loaded Successfully" in out
