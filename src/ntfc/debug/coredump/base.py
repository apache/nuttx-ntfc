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

"""Abstract base class for coredump handlers."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

###############################################################################
# Class: CoredumpHandler
###############################################################################


class CoredumpHandler(ABC):
    """Abstract base class for coredump collection handlers.

    Concrete implementations provide a specific collection method such as
    GDB, fastboot, or Y-Modem.  Handlers can be toggled at runtime via
    :meth:`enable` / :meth:`disable`.
    """

    def __init__(self) -> None:
        """Initialize :class:`CoredumpHandler` with enabled state."""
        self._enabled: bool = True

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the handler identifier string.

        :return: A short, unique name (e.g. ``"gdb"``, ``"fastboot"``).
        """

    @property
    @abstractmethod
    def priority(self) -> int:
        """Return the handler selection priority.

        Lower values are preferred when multiple handlers are available.

        :return: Non-negative integer priority.
        """

    def is_available(self) -> bool:
        """Return ``True`` if the handler can currently collect a coredump.

        Default ``True``; override for handlers with a real runtime
        precondition (e.g. a connected device or running process).

        :return: Availability flag.
        """
        return True

    @abstractmethod
    def collect(self, output_dir: "Path", prefix: str) -> bool:
        """Collect a coredump and write it under *output_dir*.

        :param output_dir: Directory where the coredump file is written.
        :param prefix: Filename prefix for the output file.
        :return: ``True`` on success, ``False`` on failure.
        """

    def enable(self) -> None:
        """Enable this handler for coredump collection."""
        self._enabled = True

    def disable(self) -> None:
        """Disable this handler so it is skipped during collection."""
        self._enabled = False

    def is_enabled(self) -> bool:
        """Return ``True`` if this handler is currently enabled.

        :return: Enabled flag.
        """
        return self._enabled
