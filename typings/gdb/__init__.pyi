# SPDX-License-Identifier: Apache-2.0
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""Typing stub for the gdb module available inside a GDB process."""

from typing import Any, Callable, List

BP_WATCHPOINT: int
COMMAND_USER: int

class error(Exception): ...

class Breakpoint:
    def __init__(
        self, spec: str, type: int = ..., internal: bool = ...
    ) -> None: ...
    def stop(self) -> bool: ...
    def delete(self) -> None: ...
    def is_valid(self) -> bool: ...

class Command:
    def __init__(self, name: str, command_class: int) -> None: ...
    def invoke(self, args: str, from_tty: bool) -> Any: ...

class Event: ...

class BreakpointEvent(Event):
    breakpoints: List[Breakpoint]

class SignalEvent(Event):
    stop_signal: str

class ExitedEvent(Event): ...

class _EventRegistry:
    def connect(self, callback: Callable[[Any], None]) -> None: ...
    def disconnect(self, callback: Callable[[Any], None]) -> None: ...

class _Events:
    stop: _EventRegistry
    exited: _EventRegistry

events: _Events

def execute(command: str, to_string: bool = ...) -> Any: ...
def string_to_argv(args: str) -> List[str]: ...
