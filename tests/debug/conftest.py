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

"""Shared fixtures for debug tests: a fake in-GDB ``gdb`` module."""

import shlex
import sys
import types
from typing import Any, Callable, Generator, List, Optional, Tuple

import pytest

# Plugin modules are imported both as submodules (by tests) and as
# top-level modules (by the init.py loader inside GDB).
_PLUGIN_MODULES = (
    "ntfc.debug.gdb.plugin.autobp",
    "ntfc.debug.gdb.plugin.gdbprefix",
    "ntfc.debug.gdb.plugin.init",
    "autobp",
    "gdbprefix",
)


def _breakpoint_class() -> Any:
    """Build a fresh fake ``gdb.Breakpoint`` class."""

    class FakeBreakpoint:
        instances: List["FakeBreakpoint"] = []
        valid = True
        delete_error: Optional[Exception] = None

        def __init__(
            self,
            spec: str,
            type: int = 0,  # noqa: A002
            internal: bool = False,
        ) -> None:
            self.spec = spec
            self.bp_type = type
            self.internal = internal
            self.deleted = False
            FakeBreakpoint.instances.append(self)

        def is_valid(self) -> bool:
            return self.valid

        def delete(self) -> None:
            if FakeBreakpoint.delete_error is not None:
                raise FakeBreakpoint.delete_error
            self.deleted = True

    return FakeBreakpoint


def _command_class() -> Any:
    """Build a fresh fake ``gdb.Command`` class."""

    class FakeCommand:
        registered: List[Tuple[str, "FakeCommand"]] = []

        def __init__(self, name: str, command_class: int) -> None:
            self.name = name
            FakeCommand.registered.append((name, self))

    return FakeCommand


def _event_classes() -> Tuple[Any, Any, Any]:
    """Build fresh fake GDB event registry and event classes."""

    class FakeEventRegistry:
        def __init__(self) -> None:
            self.callbacks: List[Callable[[Any], None]] = []

        def connect(self, callback: Callable[[Any], None]) -> None:
            self.callbacks.append(callback)

    class FakeBreakpointEvent:
        def __init__(self, breakpoints: Any = ()) -> None:
            self.breakpoints = breakpoints

    class FakeSignalEvent:
        def __init__(self, stop_signal: str) -> None:
            self.stop_signal = stop_signal

    return FakeEventRegistry, FakeBreakpointEvent, FakeSignalEvent


def build_fake_gdb() -> types.ModuleType:
    """Build a fake ``gdb`` module mimicking the in-GDB Python API.

    :return: Module object providing the subset of the GDB Python API
        used by the NTFC plugin scripts.
    """
    fake = types.ModuleType("gdb")

    class FakeError(Exception):
        pass

    registry_cls, bp_event_cls, signal_event_cls = _event_classes()

    executed: List[str] = []

    def execute(command: str, to_string: bool = False) -> str:
        executed.append(command)
        return ""

    fake.error = FakeError
    fake.Breakpoint = _breakpoint_class()
    fake.Command = _command_class()
    fake.BreakpointEvent = bp_event_cls
    fake.SignalEvent = signal_event_cls
    fake.BP_WATCHPOINT = 1
    fake.COMMAND_USER = 2
    fake.string_to_argv = shlex.split
    fake.events = types.SimpleNamespace(
        stop=registry_cls(), exited=registry_cls()
    )
    fake.execute = execute
    fake.executed = executed

    return fake


def _purge_plugin_modules() -> None:
    """Remove plugin modules from :data:`sys.modules`."""
    for name in _PLUGIN_MODULES:
        sys.modules.pop(name, None)


@pytest.fixture
def fake_gdb(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[types.ModuleType, None, None]:
    """Fixture: install a fake ``gdb`` module and reset plugin imports.

    Plugin modules register commands and connect events at import time,
    so they are removed from :data:`sys.modules` before and after each
    test to force a fresh import against the fake module.

    :yield: The fake ``gdb`` module.
    """
    fake = build_fake_gdb()
    monkeypatch.setitem(sys.modules, "gdb", fake)
    _purge_plugin_modules()
    yield fake
    _purge_plugin_modules()
