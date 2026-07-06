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

"""GDB controller for automated coredump generation."""

import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Set

from ntfc.log.logger import logger

if TYPE_CHECKING:
    from ntfc.debug.config import GdbConfig


###############################################################################
# Class: GdbController
###############################################################################


class GdbController:
    """Controls a GDB subprocess for remote debugging and coredump generation.

    Launches GDB in non-interactive (``-q``) mode, and either attaches
    to a remote target specified by
    :attr:`~ntfc.debug.config.GdbConfig.target` or PID-attaches to a
    local simulator process when
    :attr:`~ntfc.debug.config.GdbConfig.attach` is set, then exposes
    :meth:`generate_coredump` to write a core file.

    :param elf_path: Path to the ELF binary loaded by GDB.
    :param cfg: GDB section of the product debug configuration.
    :param pid_provider: Callable returning the simulator process PID
        for attach mode, or ``None`` when unused.
    """

    # GDB prints no interactive prompt when its stdout is a pipe, so
    # explicit markers are echoed after key command sequences: without
    # them there is no way to tell a slow command from a failed one.
    READY_MARKER = "NTFC_GDB_READY"
    ATTACH_MARKER = "NTFC_GDB_ATTACH_DONE"
    GCORE_MARKER = "NTFC_GDB_GCORE_DONE"

    # Standard crash breakpoint specs for auto_breakpoints feature.
    # dump_mini_info/dump_core_info are vendor-kernel symbols absent on
    # upstream NuttX; _assert is the public assert.c entry point present
    # on any build (with or without debug info), so auto_breakpoints
    # still plants a working crash breakpoint on a stripped image.
    CRASH_BP_SPECS = (
        "dump_assert_info",
        "dump_mini_info",
        "dump_core_info",
        "_assert",
    )

    def __init__(
        self,
        elf_path: Path,
        cfg: "GdbConfig",
        pid_provider: "Optional[Callable[[], Optional[int]]]" = None,
    ) -> None:
        """Initialize :class:`GdbController`.

        :param elf_path: Path to the ELF binary.
        :param cfg: GDB configuration object.
        :param pid_provider: Callable returning the simulator process PID
            for :attr:`~ntfc.debug.config.GdbConfig.attach` mode, or
            ``None`` when the PID is unavailable.
        """
        self._elf_path = elf_path
        self._cfg = cfg
        self._pid_provider = pid_provider
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._reader: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._attach_done = threading.Event()
        self._attached = False
        self._gcore_done = threading.Event()
        self._last_corefile: Optional[Path] = None
        self._lock = threading.Lock()
        self._corefiles: List[Path] = []
        self._consumed: "Set[Path]" = set()
        self._corefile_cond = threading.Condition(self._lock)

    def start(self, timeout: float = 30.0) -> bool:
        """Start GDB and attach to the configured remote target or PID.

        Spawns ``<cfg.gdb_path> -q -nx <elf_path>`` (optionally prefixed
        with ``sudo`` in attach mode), optionally sourcing the NTFC
        in-GDB plugin and any NuttX plugin, configuring the OS ABI if
        specified, waits for the readiness marker, then either sends
        ``attach <pid>`` (when :attr:`~ntfc.debug.config.GdbConfig.attach`
        is set) or ``target remote <cfg.target>`` and verifies that GDB
        reports a successful attach.  User configuration files
        (``.gdbinit``) are skipped for a deterministic environment.

        :param timeout: Seconds to wait for GDB readiness and for the
            attach to complete before giving up.
        :return: ``True`` on success, ``False`` on launch failure,
            timeout, process exit, or failed attach.
        """
        cmd = self._build_argv()

        self._ready.clear()
        self._attach_done.clear()
        self._attached = False
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            logger.warning(
                f"gdb: failed to launch {self._cfg.gdb_path}: {exc}"
            )
            return False
        self._reader = threading.Thread(
            target=self._read_stdout, name="GdbReader", daemon=True
        )
        self._reader.start()

        if not self._ready.wait(timeout=timeout):
            logger.warning("gdb: timed out waiting for prompt")
            self._terminate()
            return False

        if self._process.poll() is not None:
            logger.warning("gdb: process exited before prompt")
            return False

        if self._cfg.attach:
            pid = self._pid_provider() if self._pid_provider else None
            if pid is None:
                logger.warning("gdb: attach requested but no PID available")
                self._terminate()
                return False
            return self._verify_attach(f"attach {pid}", timeout)

        if self._cfg.target:
            return self._verify_attach(
                f"target remote {self._cfg.target}", timeout
            )

        return True

    def _build_argv(self) -> List[str]:
        """Build the GDB command-line invocation.

        Prefixes ``sudo`` in attach mode when
        :attr:`~ntfc.debug.config.GdbConfig.use_sudo` is set, then adds
        the NTFC in-GDB plugin, NuttX plugin, and OS ABI options as
        configured.

        :return: Full argv list to pass to :class:`subprocess.Popen`.
        """
        cmd: List[str] = []
        if self._cfg.attach and self._cfg.use_sudo:
            cmd.append("sudo")
        cmd.extend(
            [
                self._cfg.gdb_path,
                "-q",
                "-nx",
                str(self._elf_path),
                "-ex",
                "set pagination off",
                "-ex",
                "set confirm off",
            ]
        )

        if self._cfg.plugin:
            init = Path(__file__).parent / "plugin" / "init.py"
            cmd.extend(["-ex", f"source {init}"])

        if self._cfg.nx_plugin:
            cmd.extend(["-ex", f"source {self._cfg.nx_plugin}"])

        if self._cfg.osabi:
            cmd.extend(["-ex", f"set osabi {self._cfg.osabi}"])

        cmd.extend(["-ex", f"echo {self.READY_MARKER}\\n"])
        return cmd

    def _verify_attach(self, command: str, timeout: float) -> bool:
        """Send an attach command and verify GDB reports success.

        Sends the attach command and waits for the attach marker. On timeout,
        logs a timeout warning. On failure (marker received but attach
        unsuccessful), logs a mode-specific warning:

        * For PID attach (``attach <pid>``), suggests checking
          ``kernel.yama.ptrace_scope`` or setting ``use_sudo``.
        * For remote attach (``target remote <target>``), logs a generic
          attach failure message.

        :param command: ``attach <pid>`` or ``target remote <target>``.
        :param timeout: Seconds to wait for the attach marker.
        :return: ``True`` when GDB confirmed the attach, ``False`` on
            timeout or failed attach.
        """
        self._send(f"{command}\n")
        self._send(f"echo {self.ATTACH_MARKER}\\n\n")

        if not self._attach_done.wait(timeout=timeout):
            logger.warning(f"gdb: timed out waiting for attach ({command})")
            self._terminate()
            return False

        if not self._attached:
            if self._cfg.attach:
                logger.warning(
                    f"gdb: attach failed ({command}); check "
                    f"kernel.yama.ptrace_scope or set gdb.use_sudo "
                    f"(see Documentation/debug/gdb.rst)"
                )
            else:
                logger.warning(f"gdb: failed to attach ({command})")
            self._terminate()
            return False

        return True

    def setup(self, result_dir: str) -> None:
        """Send post-attach setup commands to GDB.

        When the in-GDB plugin is enabled the coredump output directory
        is configured via ``ntfcsetoutdir``.  All commands from
        :attr:`~ntfc.debug.config.GdbConfig.setup_cmds` are sent
        afterwards. If :attr:`~ntfc.debug.config.GdbConfig.auto_breakpoints`
        is enabled, standard crash breakpoints are planted and
        ``continue`` is sent to resume execution.

        :param result_dir: Session result directory used for coredumps.
        """
        if self._cfg.plugin:
            self._send(f"ntfcsetoutdir {result_dir}\n")

        for cmd in self._cfg.setup_cmds:
            self._send(f"{cmd}\n")

        if self._cfg.auto_breakpoints:
            gcore = self._cfg.gcore_cmd
            for spec in self.CRASH_BP_SPECS:
                self._send(
                    f"ntfcautobp bp {spec} ntfcautogcore"
                    f" -d $RESULT_DIR -n crash {gcore};bt\n"
                )
            mmleak = (
                f"ntfcmmleak -d $RESULT_DIR {gcore};"
                if self._cfg.mmleak
                else ""
            )
            self._send(
                f"ntfcautobp bp reboot_notifier_call_chain"
                f" {mmleak}ntfcautopoweroffcheck\n"
            )
            self._send("continue\n")

    def stop(self) -> None:
        """Quit GDB and clean up the subprocess and reader thread."""
        self._send("quit\n")
        if self._process is not None:
            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._terminate()
        if self._reader is not None:
            self._reader.join(timeout=5.0)

    def generate_coredump(
        self, output_dir: Path, prefix: str, timeout: float = 300.0
    ) -> Optional[Path]:
        """Send a gcore command (via cfg.gcore_cmd) and wait for writing.

        The returned corefile is marked consumed so a later
        :meth:`wait_corefile` call (e.g. for an unrelated crash-aware
        harvest) can never hand out this same file.

        :param output_dir: Directory where the corefile is placed.
        :param prefix: Filename stem for the generated corefile.
        :param timeout: Seconds to wait for the gcore command to finish.
        :return: :class:`~pathlib.Path` to the corefile, or ``None`` on
            failure or timeout.
        """
        with self._lock:
            self._gcore_done.clear()
            self._last_corefile = None

        corefile = output_dir / f"{prefix}.core"
        self._send(f"{self._cfg.gcore_cmd} {corefile}\n")
        self._send(f"echo {self.GCORE_MARKER}\\n\n")

        if not self._gcore_done.wait(timeout=timeout):
            logger.warning("gdb: timed out waiting for gcore")
            return None

        with self._lock:
            if self._last_corefile is None:
                logger.warning("gdb: gcore failed to produce a corefile")
                return None
            self._consumed.add(self._last_corefile)
            return self._last_corefile

    def is_running(self) -> bool:
        """Return ``True`` if the GDB process is alive.

        :return: ``True`` when the process exists and polls as running.
        """
        return self._process is not None and self._process.poll() is None

    def _next_unconsumed_corefile(self) -> Optional[Path]:
        """Return the newest recorded corefile not yet handed out.

        Must be called while holding :attr:`_lock` (or ``_corefile_cond``).

        :return: Corefile path, or ``None`` if none are available.
        """
        for corefile in reversed(self._corefiles):
            if corefile not in self._consumed:
                return corefile
        return None

    def wait_corefile(self, timeout: float) -> Optional[Path]:
        """Return the newest not-yet-consumed corefile, waiting if needed.

        A corefile already recorded (but not yet handed out via this
        method or :meth:`generate_coredump`) at call time is returned
        immediately -- this synchronizes with coredumps the in-GDB
        plugin can generate autonomously (``ntfcautogcore`` on a crash
        breakpoint) *before* the Python side starts waiting for one.
        Each corefile is handed out at most once.

        :param timeout: Seconds to wait when none is immediately available.
        :return: Corefile path, or ``None`` on timeout.
        """
        with self._corefile_cond:
            if self._next_unconsumed_corefile() is None:
                self._corefile_cond.wait_for(
                    lambda: self._next_unconsumed_corefile() is not None,
                    timeout=timeout,
                )
            corefile = self._next_unconsumed_corefile()
            if corefile is not None:
                self._consumed.add(corefile)
            return corefile

    @property
    def saved_corefiles(self) -> "List[Path]":
        """Return all corefiles recorded this session."""
        with self._corefile_cond:
            return list(self._corefiles)

    def _send(self, command: str) -> None:
        r"""Write *command* to GDB's stdin.

        No-ops silently when the process is not running.

        :param command: Raw GDB command string (should end with ``\n``).
        """
        if self._process is None or self._process.stdin is None:
            return
        try:
            self._process.stdin.write(command.encode())
            self._process.stdin.flush()
        except OSError as exc:
            logger.debug(f"gdb: stdin write failed: {exc}")

    def _terminate(self) -> None:
        """Forcibly terminate the GDB process and reap it."""
        if self._process is not None:  # pragma: no branch
            self._process.terminate()
            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

    def _read_stdout(self) -> None:
        """Background thread: parse GDB stdout and set synchronisation events.

        Recognises:

        * :attr:`READY_MARKER` / ``(gdb)`` / ``Type "help"`` — sets
          :attr:`_ready`
        * ``Remote debugging using`` / ``Attaching to program`` —
          records a successful attach
        * :attr:`ATTACH_MARKER` — sets :attr:`_attach_done`
        * ``Saved corefile`` — parses the corefile path
        * :attr:`GCORE_MARKER` — sets :attr:`_gcore_done` (with no
          corefile recorded this signals a failed ``gcore``)
        * EOF — sets all events to unblock any waiters
        """
        if (
            self._process is None or self._process.stdout is None
        ):  # pragma: no cover
            self._ready.set()
            self._attach_done.set()
            self._gcore_done.set()
            return

        for raw_line in self._process.stdout:
            line = raw_line.decode(errors="replace").rstrip()
            logger.debug(f"gdb< {line}")

            if (
                self.READY_MARKER in line
                or "(gdb)" in line
                or 'Type "help"' in line
            ):
                self._ready.set()

            if (
                "Remote debugging using" in line
                or "Attaching to program" in line
            ):
                self._attached = True

            if self.ATTACH_MARKER in line:
                self._attach_done.set()

            if "Saved corefile" in line:
                parts = line.split()
                corefile_path = Path(parts[-1])
                with self._corefile_cond:
                    self._last_corefile = corefile_path
                    self._corefiles.append(corefile_path)
                    self._corefile_cond.notify_all()

            if self.GCORE_MARKER in line:
                self._gcore_done.set()

        # EOF — unblock any waiters so they can observe the failure
        self._ready.set()  # pragma: no cover
        self._attach_done.set()  # pragma: no cover
        self._gcore_done.set()  # pragma: no cover
