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

import io
import os
import threading
import time
from typing import TYPE_CHECKING, BinaryIO, Generator, Iterator, List, Tuple
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from ntfc.debug.config import GdbConfig
from ntfc.debug.gdb.controller import GdbController


def _cfg(target: str = "", **kwargs: object) -> GdbConfig:
    return GdbConfig({"target": target, **kwargs})


def _make_stdout(lines: List[str]) -> io.BytesIO:
    """Return a BytesIO that yields the given lines when iterated."""
    content = "".join(line + "\n" for line in lines)
    buf = io.BytesIO(content.encode())
    return buf


def _make_process(
    stdout_lines: List[str],
    returncode: "int | None" = None,
) -> MagicMock:
    proc = MagicMock()
    proc.stdout = _make_stdout(stdout_lines)
    proc.stdin = MagicMock()
    proc.returncode = returncode
    proc.poll.return_value = returncode
    proc.wait.return_value = 0
    return proc


def _pipe_process() -> Tuple[MagicMock, BinaryIO]:
    """Create a mock process backed by a real OS pipe.

    Returns ``(proc, write_file)`` where *write_file* is the writable end.
    The caller must close *write_file* when done.
    """
    r_fd, w_fd = os.pipe()
    r_file = os.fdopen(r_fd, "rb")
    w_file = os.fdopen(w_fd, "wb", buffering=0)
    proc: MagicMock = MagicMock()
    proc.stdout = r_file
    proc.stdin = MagicMock()
    proc.returncode = None
    proc.poll.return_value = None
    proc.wait.return_value = 0
    return proc, w_file


@pytest.fixture
def elf(tmp_path: "Path") -> "Path":
    p = tmp_path / "app.elf"
    p.write_bytes(b"\x7fELF")
    return p


class TestGdbControllerStart:
    def test_start_returns_true_when_prompt_appears(self, elf: "Path"):
        proc = _make_process(["Reading symbols from app.elf...", "(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            result = ctrl.start(timeout=5.0)
        assert result is True

    def test_start_returns_true_on_type_help_prompt(self, elf: "Path"):
        proc = _make_process(['Type "help" for more information.'])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            result = ctrl.start(timeout=5.0)
        assert result is True

    def test_start_returns_false_when_gdb_missing(self, elf: "Path"):
        with patch(
            "subprocess.Popen", side_effect=FileNotFoundError("no gdb")
        ):
            ctrl = GdbController(elf, _cfg(gdb_path="missing-gdb"))
            result = ctrl.start(timeout=5.0)
        assert result is False
        assert ctrl.is_running() is False

    def test_start_returns_true_on_ready_marker(self, elf: "Path"):
        proc = _make_process([GdbController.READY_MARKER])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            result = ctrl.start(timeout=5.0)
        assert result is True

    def test_start_returns_false_on_timeout(self, elf: "Path"):
        proc = _make_process([])  # no prompt ever
        block = threading.Event()

        class BlockingStdout:
            def __iter__(self) -> Iterator[bytes]:
                block.wait()  # block until test ends
                return iter([])

        proc.stdout = BlockingStdout()

        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            result = ctrl.start(timeout=0.05)
        block.set()  # unblock the reader thread
        assert result is False

    def test_start_returns_false_when_process_exits_immediately(
        self, elf: "Path"
    ):
        proc = _make_process(["(gdb) "], returncode=1)
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            result = ctrl.start(timeout=5.0)
        assert result is False

    def test_start_sends_target_remote_when_target_set(self, elf: "Path"):
        proc = _make_process(
            [
                "(gdb) ",
                "Remote debugging using localhost:1234",
                GdbController.ATTACH_MARKER,
            ]
        )
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg(target="localhost:1234"))
            result = ctrl.start(timeout=5.0)
        assert result is True
        written = b"".join(
            call.args[0] for call in proc.stdin.write.call_args_list
        )
        assert b"target remote localhost:1234" in written

    def test_start_returns_false_when_attach_fails(self, elf: "Path"):
        # error output instead of "Remote debugging using", then marker
        proc = _make_process(
            [
                "(gdb) ",
                "localhost:1234: Connection refused.",
                GdbController.ATTACH_MARKER,
            ]
        )
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg(target="localhost:1234"))
            result = ctrl.start(timeout=5.0)
        assert result is False
        proc.terminate.assert_called_once()

    def test_remote_attach_failure_logs_generic_message(
        self, elf: "Path", caplog: object
    ) -> None:
        """Remote attach failure should not mention ptrace_scope."""
        proc = _make_process(
            [
                "(gdb) ",
                "localhost:1234: Connection refused.",
                GdbController.ATTACH_MARKER,
            ]
        )
        with patch("subprocess.Popen", return_value=proc):
            with caplog.at_level("WARNING"):  # type: ignore[attr-defined]
                ctrl = GdbController(elf, _cfg(target="localhost:1234"))
                result = ctrl.start(timeout=5.0)
        assert result is False
        assert "ptrace" not in caplog.text  # type: ignore[attr-defined]
        assert "failed to attach" in caplog.text  # type: ignore[attr-defined]

    def test_start_returns_false_on_attach_timeout(self, elf: "Path"):
        block = threading.Event()

        class BlockAfterReady:
            def __iter__(self) -> Generator[bytes, None, None]:
                yield b"(gdb) \n"
                block.wait()  # no attach marker ever arrives

        proc = _make_process([])
        proc.stdout = BlockAfterReady()

        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg(target="localhost:1234"))
            result = ctrl.start(timeout=0.05)
        block.set()
        assert result is False
        proc.terminate.assert_called_once()

    def test_start_does_not_send_target_remote_when_target_empty(
        self, elf: "Path"
    ):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg(target=""))
            ctrl.start(timeout=5.0)
        written = b"".join(
            call.args[0] for call in proc.stdin.write.call_args_list
        )
        assert b"target remote" not in written


class TestGdbControllerCommandLine:
    def test_start_uses_default_gdb_path(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc) as popen:
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
        argv = popen.call_args.args[0]
        assert argv[0] == "gdb"
        assert argv[1] == "-q"
        assert argv[2] == "-nx"
        assert argv[3] == str(elf)
        assert "set pagination off" in argv
        assert "set confirm off" in argv
        assert f"echo {GdbController.READY_MARKER}\\n" in argv

    def test_start_uses_custom_gdb_path(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc) as popen:
            ctrl = GdbController(elf, _cfg(gdb_path="gdb-multiarch"))
            ctrl.start(timeout=5.0)
        argv = popen.call_args.args[0]
        assert argv[0] == "gdb-multiarch"

    def test_start_sources_plugin_when_enabled(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc) as popen:
            ctrl = GdbController(elf, _cfg(plugin=True))
            ctrl.start(timeout=5.0)
        argv = popen.call_args.args[0]
        sourced = [a for a in argv if a.startswith("source ")]
        assert len(sourced) == 1
        assert sourced[0].endswith("plugin/init.py")

    def test_start_does_not_source_plugin_by_default(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc) as popen:
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
        argv = popen.call_args.args[0]
        assert not any(a.startswith("source ") for a in argv)

    def test_start_sources_nx_plugin_after_ntfc_plugin(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc) as popen:
            ctrl = GdbController(
                elf, _cfg(plugin=True, nx_plugin="/nx/gdbinit.py")
            )
            ctrl.start(timeout=5.0)
        argv = popen.call_args.args[0]
        sourced = [a for a in argv if a.startswith("source ")]
        assert len(sourced) == 2
        assert sourced[0].endswith("plugin/init.py")
        assert sourced[1] == "source /nx/gdbinit.py"

    def test_start_sets_osabi_when_configured(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc) as popen:
            ctrl = GdbController(elf, _cfg(osabi="none"))
            ctrl.start(timeout=5.0)
        assert "set osabi none" in popen.call_args.args[0]

    def test_start_no_osabi_by_default(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc) as popen:
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
        assert not any(
            a.startswith("set osabi") for a in popen.call_args.args[0]
        )


class TestGdbControllerAttach:
    def _attach_cfg(self, **kw: object) -> GdbConfig:
        return GdbConfig({"attach": True, **kw})

    def test_attach_success(self, elf: "Path"):
        proc = _make_process(
            [
                "(gdb) ",
                "Attaching to program: /x/nuttx, process 4242",
                GdbController.ATTACH_MARKER,
            ]
        )
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(
                elf, self._attach_cfg(), pid_provider=lambda: 4242
            )
            assert ctrl.start(timeout=5.0) is True
        written = b"".join(c.args[0] for c in proc.stdin.write.call_args_list)
        assert b"attach 4242\n" in written

    def test_attach_fails_without_pid(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(
                elf, self._attach_cfg(), pid_provider=lambda: None
            )
            assert ctrl.start(timeout=5.0) is False
        proc.terminate.assert_called_once()

    def test_attach_fails_without_provider(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, self._attach_cfg())
            assert ctrl.start(timeout=5.0) is False

    def test_attach_denied_reports_failure(self, elf: "Path"):
        # ptrace denied: error text instead of "Attaching to program"
        proc = _make_process(
            [
                "(gdb) ",
                "ptrace: Operation not permitted.",
                GdbController.ATTACH_MARKER,
            ]
        )
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(
                elf, self._attach_cfg(), pid_provider=lambda: 4242
            )
            assert ctrl.start(timeout=5.0) is False
        proc.terminate.assert_called_once()

    def test_attach_denied_logs_ptrace_guidance(
        self, elf: "Path", caplog: object
    ) -> None:
        """PID attach denied should mention ptrace_scope guidance."""
        proc = _make_process(
            [
                "(gdb) ",
                "ptrace: Operation not permitted.",
                GdbController.ATTACH_MARKER,
            ]
        )
        with patch("subprocess.Popen", return_value=proc):
            with caplog.at_level("WARNING"):  # type: ignore[attr-defined]
                ctrl = GdbController(
                    elf, self._attach_cfg(), pid_provider=lambda: 4242
                )
                result = ctrl.start(timeout=5.0)
        assert result is False
        assert "ptrace_scope" in caplog.text  # type: ignore[attr-defined]

    def test_attach_use_sudo_prefixes_argv(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc) as popen:
            ctrl = GdbController(
                elf,
                self._attach_cfg(use_sudo=True),
                pid_provider=lambda: 1,
            )
            ctrl.start(timeout=5.0)
        argv = popen.call_args.args[0]
        assert argv[0] == "sudo"
        assert argv[1] == "gdb"


class TestGdbControllerSetup:
    def _written(self, proc: MagicMock) -> bytes:
        return b"".join(
            call.args[0] for call in proc.stdin.write.call_args_list
        )

    def test_setup_sends_outdir_when_plugin_enabled(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg(plugin=True))
            ctrl.start(timeout=5.0)
            ctrl.setup("/tmp/results")
        assert b"ntfcsetoutdir /tmp/results\n" in self._written(proc)

    def test_setup_skips_outdir_without_plugin(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
            ctrl.setup("/tmp/results")
        assert b"ntfcsetoutdir" not in self._written(proc)

    def test_setup_sends_setup_cmds(self, elf: "Path"):
        cmds = ["break main", "continue"]
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg(setup_cmds=cmds))
            ctrl.start(timeout=5.0)
            ctrl.setup("/tmp/results")
        written = self._written(proc)
        assert b"break main\n" in written
        assert b"continue\n" in written

    def test_setup_plants_auto_breakpoints(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg(plugin=True, auto_breakpoints=True))
            ctrl.start(timeout=5.0)
            ctrl.setup("/results")
        written = self._written(proc).decode()
        for spec in GdbController.CRASH_BP_SPECS:
            assert (
                f"ntfcautobp bp {spec} ntfcautogcore -d $RESULT_DIR"
                f" -n crash gcore;bt\n" in written
            )
        assert (
            "ntfcautobp bp reboot_notifier_call_chain"
            " ntfcautopoweroffcheck\n" in written
        )
        assert written.endswith("continue\n")

    def test_setup_auto_breakpoints_with_mmleak(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(
                elf,
                _cfg(plugin=True, auto_breakpoints=True, mmleak=True),
            )
            ctrl.start(timeout=5.0)
            ctrl.setup("/results")
        assert (
            "ntfcautobp bp reboot_notifier_call_chain"
            " ntfcmmleak -d $RESULT_DIR gcore;ntfcautopoweroffcheck\n"
            in self._written(proc).decode()
        )

    def test_setup_no_auto_breakpoints_by_default(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg(plugin=True))
            ctrl.start(timeout=5.0)
            ctrl.setup("/results")
        assert b"ntfcautobp" not in self._written(proc)


class TestGdbControllerGenerateCoredump:
    def test_generate_coredump_returns_path_on_success(
        self, elf: "Path", tmp_path: "Path"
    ) -> None:
        """Use a real pipe so the reader blocks until we feed the response."""
        proc, w_file = _pipe_process()
        corefile = tmp_path / "test.core"

        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            w_file.write(b"(gdb) \n")
            start_ok = ctrl.start(timeout=5.0)

        assert start_ok is True

        w_file.write(f"Saved corefile {corefile}\n".encode())
        w_file.write(f"{GdbController.GCORE_MARKER}\n".encode())
        result = ctrl.generate_coredump(tmp_path, "test", timeout=5.0)
        # Close write end → EOF → reader exits; join to avoid ResourceWarning
        w_file.close()
        ctrl.stop()
        proc.stdout.close()

        assert result == corefile

    def test_generate_coredump_returns_none_when_gcore_fails(
        self, elf: "Path", tmp_path: "Path"
    ) -> None:
        """Marker without 'Saved corefile' signals a failed gcore."""
        proc, w_file = _pipe_process()

        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            w_file.write(b"(gdb) \n")
            ctrl.start(timeout=5.0)

        w_file.write(b"Unable to fetch a corefile\n")
        w_file.write(f"{GdbController.GCORE_MARKER}\n".encode())
        result = ctrl.generate_coredump(tmp_path, "test", timeout=5.0)
        w_file.close()
        ctrl.stop()
        proc.stdout.close()

        assert result is None

    def test_generate_coredump_returns_none_on_timeout(
        self, elf: "Path", tmp_path: "Path"
    ) -> None:
        block = threading.Event()

        class BlockAfterPrompt:
            def __iter__(self) -> Generator[bytes, None, None]:
                yield b"(gdb) \n"
                block.wait()  # block: no "Saved corefile" ever arrives

        proc = _make_process([])
        proc.stdout = BlockAfterPrompt()

        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
            result = ctrl.generate_coredump(tmp_path, "test", timeout=0.05)
        block.set()
        assert result is None

    def test_generate_coredump_returns_none_when_process_dies(
        self, elf: "Path", tmp_path: "Path"
    ) -> None:
        """Closing the write end mid-wait simulates process death."""
        proc, w_file = _pipe_process()

        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            w_file.write(b"(gdb) \n")
            ctrl.start(timeout=5.0)

        def close_after_delay() -> None:
            import time

            time.sleep(0.05)
            w_file.close()

        t = threading.Thread(target=close_after_delay)
        t.start()
        result = ctrl.generate_coredump(tmp_path, "test", timeout=5.0)
        t.join()
        # Reader exited due to EOF; join + close to avoid ResourceWarning
        ctrl.stop()
        proc.stdout.close()

        assert result is None

    def test_generate_coredump_uses_gcore_cmd(
        self, elf: "Path", tmp_path: "Path"
    ) -> None:
        proc, w_file = _pipe_process()
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg(gcore_cmd="gcore -t nuttx"))
            w_file.write(b"(gdb) \n")
            ctrl.start(timeout=5.0)
        w_file.write(f"{GdbController.GCORE_MARKER}\n".encode())
        ctrl.generate_coredump(tmp_path, "t", timeout=5.0)
        w_file.close()
        ctrl.stop()
        proc.stdout.close()
        written = b"".join(
            call.args[0] for call in proc.stdin.write.call_args_list
        )
        assert f"gcore -t nuttx {tmp_path}/t.core\n".encode() in written


class TestGdbControllerIsRunning:
    def test_is_running_true_when_process_alive(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
            assert ctrl.is_running() is True

    def test_is_running_false_before_open(self, elf: "Path"):
        ctrl = GdbController(elf, _cfg())
        assert ctrl.is_running() is False

    def test_is_running_false_after_process_exits(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
        # Simulate process exit after startup: only poll() notices
        proc.poll.return_value = 0
        assert ctrl.is_running() is False


class TestGdbControllerStop:
    def test_stop_sends_quit(self, elf: "Path"):
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
            ctrl.stop()
        written = b"".join(
            call.args[0] for call in proc.stdin.write.call_args_list
        )
        assert b"quit" in written

    def test_stop_terminates_if_wait_times_out(self, elf: "Path"):
        import subprocess as sp

        proc = _make_process(["(gdb) "])
        # quit wait times out, post-terminate wait reaps the process
        proc.wait.side_effect = [
            sp.TimeoutExpired(cmd="gdb", timeout=5),
            0,
        ]
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
            ctrl.stop()
        proc.terminate.assert_called_once()
        proc.kill.assert_not_called()

    def test_stop_kills_if_terminate_wait_times_out(self, elf: "Path"):
        import subprocess as sp

        proc = _make_process(["(gdb) "])
        # quit wait and post-terminate wait time out, kill reaps
        proc.wait.side_effect = [
            sp.TimeoutExpired(cmd="gdb", timeout=5),
            sp.TimeoutExpired(cmd="gdb", timeout=5),
            0,
        ]
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
            ctrl.stop()
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()

    def test_stop_before_start_does_not_raise(self, elf: "Path"):
        ctrl = GdbController(elf, _cfg())
        ctrl.stop()  # must not raise

    def test_send_swallows_oserror(self, elf: "Path"):
        """OSError on stdin.write must be caught and logged, not raised."""
        proc = _make_process(["(gdb) "])
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            ctrl.start(timeout=5.0)
        # Simulate broken pipe after open
        proc.stdin.write.side_effect = OSError("broken pipe")
        ctrl.stop()  # calls _send("quit\n") → OSError caught internally


class TestGdbControllerCorefileLedger:
    def test_unsolicited_saved_corefile_recorded(
        self, elf: "Path", tmp_path: "Path"
    ) -> None:
        proc, w_file = _pipe_process()
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            w_file.write(b"(gdb) \n")
            ctrl.start(timeout=5.0)
        core = tmp_path / "crash.2026.core"
        w_file.write(f"Saved corefile {core}\n".encode())
        result = ctrl.wait_corefile(timeout=5.0)
        w_file.close()
        ctrl.stop()
        proc.stdout.close()
        assert result == core
        assert ctrl.saved_corefiles == [core]

    def test_wait_corefile_times_out(self, elf: "Path") -> None:
        proc, w_file = _pipe_process()
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            w_file.write(b"(gdb) \n")
            ctrl.start(timeout=5.0)
        result = ctrl.wait_corefile(timeout=0.05)
        w_file.close()
        ctrl.stop()
        proc.stdout.close()
        assert result is None

    def test_wait_corefile_ignores_earlier_cores(
        self, elf: "Path", tmp_path: "Path"
    ) -> None:
        proc, w_file = _pipe_process()
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            w_file.write(b"(gdb) \n")
            ctrl.start(timeout=5.0)
        w_file.write(f"Saved corefile {tmp_path}/old.core\n".encode())
        ctrl.wait_corefile(timeout=5.0)  # consume the first
        result = ctrl.wait_corefile(timeout=0.05)  # nothing new
        w_file.close()
        ctrl.stop()
        proc.stdout.close()
        assert result is None
        assert len(ctrl.saved_corefiles) == 1

    def test_wait_corefile_returns_corefile_recorded_before_call(
        self, elf: "Path", tmp_path: "Path"
    ) -> None:
        """Regression test for the baseline race: a corefile already
        recorded (e.g. the in-GDB auto-dump firing within ~1s of a
        crash) before :meth:`~GdbController.wait_corefile` is even
        called must still be returned, not lost to a stale
        "wait for growth beyond baseline" snapshot.
        """
        proc, w_file = _pipe_process()
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            w_file.write(b"(gdb) \n")
            ctrl.start(timeout=5.0)
        core = tmp_path / "crash.2026.core"
        w_file.write(f"Saved corefile {core}\n".encode())
        # Deterministically wait until the reader thread has recorded
        # the corefile BEFORE calling wait_corefile, so the test does
        # not depend on thread-scheduling luck to reproduce the race.
        deadline = time.monotonic() + 5.0
        while not ctrl.saved_corefiles and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ctrl.saved_corefiles == [core]
        result = ctrl.wait_corefile(timeout=1.0)
        w_file.close()
        ctrl.stop()
        proc.stdout.close()
        assert result == core

    def test_generate_coredump_result_not_returned_by_later_wait_corefile(
        self, elf: "Path", tmp_path: "Path"
    ) -> None:
        """A corefile already handed out via generate_coredump (the
        pull path) must never be re-handed-out by a later
        wait_corefile call for an unrelated crash-aware harvest.
        """
        proc, w_file = _pipe_process()
        corefile = tmp_path / "pull.core"
        with patch("subprocess.Popen", return_value=proc):
            ctrl = GdbController(elf, _cfg())
            w_file.write(b"(gdb) \n")
            ctrl.start(timeout=5.0)
        w_file.write(f"Saved corefile {corefile}\n".encode())
        w_file.write(f"{GdbController.GCORE_MARKER}\n".encode())
        result = ctrl.generate_coredump(tmp_path, "pull", timeout=5.0)
        assert result == corefile
        later = ctrl.wait_corefile(timeout=0.05)
        w_file.close()
        ctrl.stop()
        proc.stdout.close()
        assert later is None
