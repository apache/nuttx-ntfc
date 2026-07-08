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

"""Ymodem-based coredump handler."""

import datetime
import re
from typing import TYPE_CHECKING, Optional

from ntfc.debug.coredump.base import CoredumpHandler
from ntfc.device.common import CmdStatus

if TYPE_CHECKING:
    from pathlib import Path

    from ntfc.device.common import DeviceCommon
    from ntfc.lib.ymodem.controller import YmodemController


class YmodemHandler(CoredumpHandler):
    """Coredump handler that collects via Ymodem serial protocol.

    Locates the corefile on the device using shell commands, then
    transfers it using
    :class:`~ntfc.lib.ymodem.controller.YmodemController`.

    :param controller: Ymodem controller managing the file transfer.
    :param device: Device instance used to send shell commands.
    """

    _COREDIR = "/log/offlinelog"

    def __init__(
        self,
        controller: "YmodemController",
        device: "DeviceCommon",
    ) -> None:
        """Initialize :class:`YmodemHandler`.

        :param controller: Ymodem controller managing the file transfer.
        :param device: Device instance used to send shell commands.
        """
        super().__init__()
        self._controller = controller
        self._device = device

    @property
    def name(self) -> str:
        """Return handler name ``"ymodem"``."""
        return "ymodem"

    @property
    def priority(self) -> int:
        """Return selection priority ``30``."""
        return 30

    def is_available(self) -> bool:
        """Return ``True`` if the controller is configured and ready.

        :return: Delegates to
            :meth:`~ntfc.lib.ymodem.controller.YmodemController.is_ready`.
        """
        return self._controller.is_ready()

    def collect(self, output_dir: "Path", prefix: str) -> bool:
        """Locate and download a corefile via Ymodem.

        Calls :meth:`_find_coredump` to rename the file on the device,
        then
        :meth:`~ntfc.lib.ymodem.controller.YmodemController.download`
        to transfer it.  The device is stopped for the duration of the
        transfer so ``sbrb.py`` gets exclusive access to the serial
        port, and restarted afterwards.

        :param output_dir: Host directory where the file is saved.
        :param prefix: Filename prefix used when renaming the corefile.
        :return: ``True`` on success, ``False`` on failure.
        """
        corefile_name = self._find_coredump(prefix)
        if corefile_name is None:
            return False

        # sbrb.py needs exclusive access to the serial port; the device
        # must release it during the transfer.
        self._device.stop()
        try:
            return self._controller.download(output_dir, corefile_name)
        finally:
            self._device.start()

    def _find_coredump(self, prefix: str) -> Optional[str]:
        """Locate and rename an unformatted core file on the device.

        Searches :attr:`_COREDIR` for a ``.core`` file that has not yet
        been timestamped.  Renames it to
        ``<prefix>.<YYYY.MM.DD_HH.MM.SS>.core`` in-place on the device.

        :param prefix: Filename prefix for the renamed corefile.
        :return: New corefile name on success, ``None`` if not found.
        """
        result = self._device.send_cmd_read_until_pattern(
            b"ls -l " + self._COREDIR.encode() + b"/",
            rb"\.core",
            timeout=20,
        )
        if result.status != CmdStatus.SUCCESS:
            return None

        core_file = self._parse_corefile(result.output)
        if core_file is None:
            return None

        ts = datetime.datetime.now().strftime("%Y.%m.%d_%H.%M.%S")
        new_name = f"{prefix}.{ts}.core"

        mv_cmd = (
            f"mv {self._COREDIR}/{core_file}" f" {self._COREDIR}/{new_name}"
        ).encode()
        self._device.send_cmd_read_until_pattern(mv_cmd, b">", timeout=60)

        return new_name

    @staticmethod
    def _parse_corefile(output: str) -> Optional[str]:
        """Find the first ``.core`` file without a timestamp in its name.

        A file is considered timestamped when its name contains a segment
        matching ``YYYY.MM.DD_HH.MM.SS``.

        :param output: Text output from ``ls`` on the device.
        :return: Core filename, or ``None`` if none found.
        """
        stamped = re.compile(r"\d{4}\.\d{2}\.\d{2}_\d{2}\.\d{2}\.\d{2}")
        for line in output.splitlines():
            m = re.search(r"(\S+\.core)", line)
            if m:
                name = m.group(1)
                if not stamped.search(name):
                    return name
        return None
