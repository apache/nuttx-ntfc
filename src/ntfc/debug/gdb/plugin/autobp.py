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

"""Automatic breakpoint handling loaded inside a GDB process.

This module is sourced by GDB (see ``init.py``) and provides custom
commands for automated coredump generation:

* ``ntfcautobp`` -- set a breakpoint/watchpoint that executes commands,
* ``ntfcsetoutdir`` -- set the output directory for coredump files,
* ``ntfcautogcore`` -- generate a timestamped coredump file,
* ``ntfcmmleak`` -- dump a coredump when NuttX ``mm leak`` reports leaks,
* ``ntfcautopoweroffcheck`` -- print a backtrace on power-off checks.
"""

import datetime
import os
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import gdb

# File used to persist the output directory across GDB invocations.
NTFC_DIR_FILE = "/tmp/.ntfc_gdb_output_dir"

# Breakpoint specs treated as crash coredump breakpoints: when one of
# them triggers, all of its siblings are deleted as well. Must stay in
# sync with GdbController.CRASH_BP_SPECS (controller.py), which plants
# the breakpoints these specs are matched against.
CRASH_COREDUMP_SPECS = (
    "dump_mini_info",
    "dump_core_info",
    "dump_assert_info",
    "_assert",
)

# Placeholder arguments resolved to the configured output directory.
DYNAMIC_DIR_ARGS = ("$RESULT_DIR", "__NTFC_DYNAMIC__")

_output_dir: Optional[str] = None


def _result_check(method: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate a command method to log its boolean result.

    :param method: Method returning a truthy value on success.
    :return: Wrapped method printing ``Success:``/``Failed:`` lines.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = method(*args, **kwargs)

        name = type(args[0]).__name__
        argstr = " ".join(map(str, args[1:-1])) if len(args) > 1 else ""

        if result:
            print(f"Success: {name} {argstr}")
        else:
            print(f"Failed: {name} {argstr}")

        return result

    return wrapper


def _output_dir_get() -> Optional[str]:
    """Return the configured output directory.

    The global variable set by ``ntfcsetoutdir`` takes precedence; the
    backup file is used as a fallback.

    :return: Output directory path or ``None`` when not configured.
    """
    if _output_dir is not None:
        return _output_dir

    if os.path.exists(NTFC_DIR_FILE):
        try:
            with open(NTFC_DIR_FILE, encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                return content
        except OSError as e:
            print(f"Could not read backup file: {e}")

    return None


def _output_dir_ensure(output_dir: str) -> bool:
    """Create the output directory when it does not exist.

    :param output_dir: Directory path to verify or create.
    :return: ``True`` when the directory exists or was created.
    """
    if os.path.isdir(output_dir):
        return True

    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")
    except OSError as e:
        print(f"Failed to create directory {output_dir}: {e}")
        return False

    return True


def _resolve_output_dir(argv: List[str]) -> Optional[str]:
    """Resolve the ``-d <dir|$RESULT_DIR>`` output directory argument.

    Shared by :class:`NtfcAutoGcore` and :class:`NtfcAutoMmleak`, whose
    commands both accept the same ``-d`` flag.

    :param argv: Parsed command arguments.
    :return: Output directory or ``None`` on error.
    """
    if len(argv) < 2:
        print("Error: No arguments provided")
        return None

    if argv[0] != "-d":
        print(f"Error: First argument must be '-d', got '{argv[0]}'")
        return None

    if argv[1] in DYNAMIC_DIR_ARGS:
        output_dir = _output_dir_get()
        if not output_dir:
            print(
                "Error: Output directory not set. "
                "Use 'ntfcsetoutdir <dir>' first."
            )
            return None
        return output_dir

    return argv[1]


def _coredump_path(output_dir: str, name: str) -> str:
    """Build a timestamped coredump file path.

    :param output_dir: Directory where the coredump is written.
    :param name: Coredump file name prefix.
    :return: Full path of the coredump file.
    """
    stamp = datetime.datetime.now().strftime("%Y.%m.%d_%H.%M.%S")
    return os.path.join(output_dir, f"{name}.{stamp}.core")


class AutoBp(gdb.Breakpoint):
    """Breakpoint that executes a list of commands when hit.

    Crash coredump breakpoints (see :data:`CRASH_COREDUMP_SPECS`) with an
    ``ntfcautogcore`` command are tracked together: when one triggers all
    of its siblings are deleted, so a single crash produces one coredump.

    :param spec: Breakpoint location or watchpoint expression.
    :param commands: GDB commands to execute when the breakpoint is hit.
    :param bp_type: ``"bp"`` for a breakpoint, ``"wp"`` for a watchpoint.
    """

    _pending_delete: "Set[AutoBp]" = set()
    _crash_coredump_breakpoints: "Dict[str, AutoBp]" = {}

    def __init__(
        self, spec: str, commands: List[str], bp_type: str = "bp"
    ) -> None:
        """Initialize :class:`AutoBp`.

        :param spec: Breakpoint location or watchpoint expression.
        :param commands: GDB commands to execute on hit.
        :param bp_type: ``"bp"`` (breakpoint) or ``"wp"`` (watchpoint).
        """
        if bp_type == "wp":
            super().__init__(spec, gdb.BP_WATCHPOINT, internal=False)
        else:
            super().__init__(spec, internal=False)
        self._cmds = commands
        self._spec = spec

        is_crash_coredump = spec in CRASH_COREDUMP_SPECS
        has_autogcore = any("ntfcautogcore" in cmd for cmd in commands)

        if is_crash_coredump and has_autogcore:
            AutoBp._crash_coredump_breakpoints[spec] = self
            print(f"Registered crash coredump breakpoint: {spec}")

    def stop(self) -> bool:
        """Execute the configured commands and mark cleanup.

        :return: ``True`` to stop the inferior (resumed by the stop
            event handler).
        """
        for cmd in self._cmds:
            try:
                print(f"Executing command: {cmd}")
                gdb.execute(cmd)
            except gdb.error as e:
                print(f"Command failed: {cmd}, error: {e}")

        if self._spec in AutoBp._crash_coredump_breakpoints:
            AutoBp._pending_delete.add(self)

            for name, bp in AutoBp._crash_coredump_breakpoints.items():
                if name != self._spec and bp is not self:
                    print(
                        f"Crash coredump triggered at {self._spec}. "
                        f"Also deleting sibling breakpoint: {name}"
                    )
                    AutoBp._pending_delete.add(bp)

            AutoBp._crash_coredump_breakpoints.clear()
        else:
            AutoBp._pending_delete.add(self)

        return True


class NtfcAutoBp(gdb.Command):
    """Command ``ntfcautobp``: set an automatic breakpoint.

    Usage: ``ntfcautobp <bp|wp> <spec> <cmd1>[;<cmd2>...]``
    """

    def __init__(self) -> None:
        """Register the ``ntfcautobp`` command."""
        super().__init__("ntfcautobp", gdb.COMMAND_USER)

    @_result_check
    def invoke(self, args: str, from_tty: bool) -> bool:
        """Create an :class:`AutoBp` from command arguments.

        :param args: Raw command arguments.
        :param from_tty: ``True`` when invoked from an interactive tty.
        :return: ``True`` when the breakpoint was created and is valid.
        """
        argv = gdb.string_to_argv(args)
        if len(argv) < 3:
            return False

        bp_type = argv[0]
        target = argv[1]
        command_str = " ".join(argv[2:]).strip()
        commands = command_str.split(";")

        if bp_type not in ("bp", "wp"):
            return False

        bp = AutoBp(spec=target, commands=commands, bp_type=bp_type)

        return bp.is_valid()


class NtfcSetOutDir(gdb.Command):
    """Command ``ntfcsetoutdir``: set the coredump output directory."""

    def __init__(self) -> None:
        """Register the ``ntfcsetoutdir`` command."""
        super().__init__("ntfcsetoutdir", gdb.COMMAND_USER)

    def invoke(self, args: str, from_tty: bool) -> None:
        """Store the output directory and persist it to a backup file.

        :param args: Raw command arguments (a single directory path).
        :param from_tty: ``True`` when invoked from an interactive tty.
        """
        global _output_dir

        argv = gdb.string_to_argv(args)
        if len(argv) != 1:
            print("Usage: ntfcsetoutdir <directory>")
            return

        output_dir = argv[0]

        if not _output_dir_ensure(output_dir):
            return

        _output_dir = output_dir

        try:
            with open(NTFC_DIR_FILE, "w", encoding="utf-8") as f:
                f.write(output_dir)
                f.flush()
            print(f"Also saved to file: {NTFC_DIR_FILE}")
        except OSError as e:
            print(f"Note: Could not write to backup file: {e}")

        print(f"NTFC Output Directory Set: {output_dir}")


class NtfcAutoGcore(gdb.Command):
    """Command ``ntfcautogcore``: generate a timestamped coredump.

    Usage: ``ntfcautogcore -d <dir|$RESULT_DIR> [-n <name>] <gcore-cmd>``
    """

    def __init__(self) -> None:
        """Register the ``ntfcautogcore`` command."""
        super().__init__("ntfcautogcore", gdb.COMMAND_USER)

    def _parse_name(self, argv: List[str]) -> Optional[Tuple[str, int]]:
        """Parse the optional ``-n <name>`` arguments.

        :param argv: Parsed command arguments.
        :return: Tuple of (name, gcore command index) or ``None``.
        """
        if len(argv) > 2 and argv[2] == "-n":
            if len(argv) <= 3:
                print("Error: -n flag requires a name argument")
                return None
            return argv[3], 4

        return "", 2

    def _verify_coredump(self, coredump: str) -> bool:
        """Verify that the generated coredump is a valid ELF file.

        :param coredump: Path of the generated coredump.
        :return: ``True`` when the file exists and has an ELF header.
        """
        if not os.path.isfile(coredump):
            print(f"Error: '{coredump}' does not exist or is not a file.\n")
            return False

        try:
            with open(coredump, "rb") as f:
                header = f.read(4)
        except OSError as e:
            print(f"Error reading '{coredump}': {e}.\n")
            return False

        if header != b"\x7fELF":
            print(f"{coredump} is not valid core file: {header!r}")
            return False

        print(f"{coredump} is valid ELF core file.\n")
        return True

    @_result_check
    def invoke(self, args: str, from_tty: bool) -> bool:
        """Generate a coredump using the configured gcore command.

        :param args: Raw command arguments.
        :param from_tty: ``True`` when invoked from an interactive tty.
        :return: ``True`` when a valid coredump was generated.
        """
        argv = gdb.string_to_argv(args)
        print(f"NtfcAutoGcore: Received args: {argv}")

        output_dir = _resolve_output_dir(argv)
        if output_dir is None:
            return False

        parsed = self._parse_name(argv)
        if parsed is None:
            return False
        name, index = parsed

        if not _output_dir_ensure(output_dir):
            return False

        coredump = _coredump_path(output_dir, name)
        print(f"Generate coredump: {coredump}")

        cmd = " ".join(argv[index:]).strip() + f" {coredump}"
        print(f"Executing gcore command: {cmd}")

        try:
            gdb.execute(cmd)
            print("gcore command executed successfully")
        except gdb.error as e:
            print(f"gcore command failed with exception: {e}")
            return False

        return self._verify_coredump(coredump)


class NtfcAutoMmleak(gdb.Command):
    """Command ``ntfcmmleak``: dump a coredump on NuttX memory leaks.

    Runs the NuttX ``mm leak`` GDB command; when leaked blocks are
    reported the leak report is written next to a generated coredump.

    Usage: ``ntfcmmleak -d <dir|$RESULT_DIR> <gcore-cmd>``
    """

    def __init__(self) -> None:
        """Register the ``ntfcmmleak`` command."""
        super().__init__("ntfcmmleak", gdb.COMMAND_USER)

    @_result_check
    def invoke(self, args: str, from_tty: bool) -> bool:
        """Check for memory leaks and generate a coredump if leaking.

        :param args: Raw command arguments.
        :param from_tty: ``True`` when invoked from an interactive tty.
        :return: ``True`` when the check completed.
        """
        argv = gdb.string_to_argv(args)
        output_dir = _resolve_output_dir(argv)
        if output_dir is None:
            return False

        coredump = _coredump_path(output_dir, "mmleak")
        gcore_cmd = " ".join(argv[2:]).strip() + f" {coredump}"

        ret = gdb.execute("mm leak", to_string=True)
        print(ret)

        match = re.search(r"Leaked (\d+) blks, (\d+) bytes", ret)
        if match and int(match.group(1)) > 0:
            result = os.path.join(output_dir, "nuttx.mmleak")
            with open(result, "w", encoding="utf-8") as f:
                f.write(ret)
            print(f"Mmleak -> {gcore_cmd}")
            print(gdb.execute(gcore_cmd, to_string=True))

        return True


class NtfcAutoPoweroffCheck(gdb.Command):
    """Command ``ntfcautopoweroffcheck``: print a backtrace."""

    def __init__(self) -> None:
        """Register the ``ntfcautopoweroffcheck`` command."""
        super().__init__("ntfcautopoweroffcheck", gdb.COMMAND_USER)

    @_result_check
    def invoke(self, args: str, from_tty: bool) -> bool:
        """Print the current backtrace.

        :param args: Raw command arguments (unused).
        :param from_tty: ``True`` when invoked from an interactive tty.
        :return: Always ``True``.
        """
        print(gdb.execute("bt"))
        return True


def gdb_autobp_stop_event(event: Any) -> None:
    """Handle GDB stop events: delete pending breakpoints and resume.

    Only stops caused exclusively by :class:`AutoBp` breakpoints are
    resumed automatically; a stop at a user breakpoint (e.g. set via
    ``setup_cmds``) leaves the inferior stopped for inspection.

    :param event: GDB stop event instance.
    """
    if isinstance(event, gdb.BreakpointEvent):
        bps = getattr(event, "breakpoints", ())
        if not all(isinstance(bp, AutoBp) for bp in bps):
            print("NTFC GDB: stop at user breakpoint, not resuming")
            return
        if AutoBp._pending_delete:
            print(
                f"NtfcAutoBp: Deleting {len(AutoBp._pending_delete)} "
                f"marked breakpoint(s)."
            )
            for bp in list(AutoBp._pending_delete):
                try:
                    bp.delete()
                    AutoBp._pending_delete.remove(bp)
                except gdb.error as e:
                    print(f"Failed to delete breakpoint: {e}")
        gdb.execute("continue")
    if isinstance(event, gdb.SignalEvent):
        if event.stop_signal == "SIGINT":
            print("NTFC GDB SIGINT Event")
        elif event.stop_signal == "SIGTERM":
            print("NTFC GDB SIGTERM Event")
            gdb.execute("q")
        else:
            print("NTFC GDB Unexpected Signal Event")


def gdb_process_exited_event(event: Any) -> None:
    """Handle GDB inferior exit events: quit GDB.

    :param event: GDB exited event instance.
    """
    print("NTFC GDB Process Exited Event")
    gdb.execute("q")


NtfcAutoBp()
NtfcSetOutDir()
NtfcAutoGcore()
NtfcAutoMmleak()
NtfcAutoPoweroffCheck()

gdb.events.stop.connect(gdb_autobp_stop_event)
gdb.events.exited.connect(gdb_process_exited_event)
