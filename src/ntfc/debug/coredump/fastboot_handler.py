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

"""Fastboot-based coredump handler."""

from typing import TYPE_CHECKING

from ntfc.debug.coredump.base import CoredumpHandler

if TYPE_CHECKING:
    from pathlib import Path

    from ntfc.lib.fastboot.controller import FastbootController


class FastbootHandler(CoredumpHandler):
    """Coredump handler that collects via fastboot memory dump.

    Delegates to
    :class:`~ntfc.lib.fastboot.controller.FastbootController` which
    runs ``fastboot oem memdump`` then ``fastboot get_staged``.

    :param controller: Fastboot controller managing the download.
    :param mem_addr: Memory start address for the dump (hex string).
    :param mem_size: Memory region size to dump (hex string).
    """

    def __init__(
        self,
        controller: "FastbootController",
        mem_addr: str,
        mem_size: str,
    ) -> None:
        """Initialize :class:`FastbootHandler`.

        :param controller: Fastboot controller managing the download.
        :param mem_addr: Memory start address (hex string).
        :param mem_size: Memory region size (hex string).
        """
        super().__init__()
        self._controller = controller
        self._mem_addr = mem_addr
        self._mem_size = mem_size

    @property
    def name(self) -> str:
        """Return handler name ``"fastboot"``."""
        return "fastboot"

    @property
    def priority(self) -> int:
        """Return selection priority ``20``."""
        return 20

    def is_available(self) -> bool:
        """Return ``True`` if the device is visible in fastboot mode.

        :return: Delegates to
            :meth:`~ntfc.lib.fastboot.controller.FastbootController\
.is_connected`.
        """
        return self._controller.is_connected()

    def collect(self, output_dir: "Path", prefix: str) -> bool:
        """Download a memory dump via fastboot.

        :param output_dir: Directory where the dump file is written.
        :param prefix: Filename stem for the output file (saved as
            ``<prefix>.bin``).
        :return: ``True`` on success, ``False`` on failure.
        """
        result = self._controller.memdump(
            self._mem_addr,
            self._mem_size,
            output_dir / f"{prefix}.bin",
        )
        return result is not None
