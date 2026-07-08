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

"""GDB-based coredump handler."""

import shutil
from typing import TYPE_CHECKING, Callable, Optional

from ntfc.debug.coredump.base import CoredumpHandler
from ntfc.log.logger import logger

if TYPE_CHECKING:
    from pathlib import Path

    from ntfc.debug.gdb.controller import GdbController


###############################################################################
# Class: GdbHandler
###############################################################################


class GdbHandler(CoredumpHandler):
    """Coredump handler that uses a running :class:`GdbController`.

    :param controller: GDB controller instance used to generate coredumps.
    :param force_panic: Optional callable that panics the device before
        the coredump is generated (``debug.gdb.force_panic``), so the
        dump captures crash state instead of a live system.
    :param crash_check: Optional callable returning ``True`` when the
        product has already crashed, in which case an in-GDB automatic
        coredump is expected instead of a pulled one.
    :param auto_dump: Whether automatic crash breakpoints are active in
        the GDB session, so a crash coredump is written by GDB itself
        and only needs to be harvested.
    """

    #: Seconds to wait for an in-GDB crash coredump to appear.
    AUTO_DUMP_TIMEOUT = 600.0

    def __init__(
        self,
        controller: "GdbController",
        force_panic: "Optional[Callable[[], bool]]" = None,
        crash_check: "Optional[Callable[[], bool]]" = None,
        auto_dump: bool = False,
    ) -> None:
        """Initialize :class:`GdbHandler`.

        :param controller: GDB controller used for coredump generation.
        :param force_panic: Optional callable forcing a device panic
            before collection.
        :param crash_check: Optional callable reporting whether the
            product has already crashed.
        :param auto_dump: Whether automatic crash coredumps are active.
        """
        super().__init__()
        self._controller = controller
        self._force_panic = force_panic
        self._crash_check = crash_check
        self._auto_dump = auto_dump

    @property
    def name(self) -> str:
        """Return the handler name ``"gdb"``.

        :return: ``"gdb"``
        """
        return "gdb"

    @property
    def priority(self) -> int:
        """Return the handler priority ``10``.

        :return: ``10``
        """
        return 10

    def is_available(self) -> bool:
        """Return ``True`` when the GDB controller process is running.

        :return: Availability flag.
        """
        return self._controller.is_running()

    def collect(self, output_dir: "Path", prefix: str) -> bool:
        """Generate or harvest a coredump via the GDB controller.

        When the product crashed and automatic crash breakpoints are
        active, the in-GDB plugin is already writing the dump: wait for
        it and move it into place. Otherwise fall back to the pull path
        (optional forced panic, then ``gcore``).

        :param output_dir: Directory where the coredump file is written.
        :param prefix: Filename prefix for the output file.
        :return: ``True`` if a corefile was created, ``False`` otherwise.
        """
        if (
            self._auto_dump
            and self._crash_check is not None
            and self._crash_check()
        ):
            return self._harvest_auto_dump(output_dir, prefix)

        if self._force_panic is not None:
            logger.debug("gdb: forcing device panic before coredump")
            if not self._force_panic():
                logger.warning("gdb: force panic failed")

        result = self._controller.generate_coredump(output_dir, prefix)
        return result is not None

    def _harvest_auto_dump(self, output_dir: "Path", prefix: str) -> bool:
        """Wait for the in-GDB auto-generated coredump and move it.

        :param output_dir: Destination directory.
        :param prefix: Destination filename prefix.
        :return: ``True`` when a corefile arrived within the window.
        """
        logger.debug("gdb: waiting for in-GDB crash coredump")
        corefile = self._controller.wait_corefile(
            timeout=self.AUTO_DUMP_TIMEOUT
        )
        if corefile is None:
            logger.warning("gdb: timed out waiting for crash coredump")
            return False

        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / f"{prefix}.core"
        shutil.move(str(corefile), dest)
        logger.debug(f"gdb: crash coredump harvested to {dest}")
        return True
