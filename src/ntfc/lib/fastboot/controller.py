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

"""Fastboot transport controller."""

import subprocess
from typing import TYPE_CHECKING, List, Optional

from ntfc.log.logger import logger

if TYPE_CHECKING:
    from pathlib import Path


class FastbootController:
    """Controls a device via the fastboot protocol.

    Provides device detection, generic command execution, and memory
    dump retrieval.  Commands that target a specific device are issued
    with the ``-s <dev_sn>`` flag automatically.

    :param dev_sn: Fastboot device serial number.
    """

    def __init__(self, dev_sn: str) -> None:
        """Initialize :class:`FastbootController`.

        :param dev_sn: Fastboot device serial number.
        """
        self._dev_sn = dev_sn

    def is_connected(self) -> bool:
        """Return ``True`` if the device is visible in fastboot mode.

        :return: ``True`` when the device serial number appears in the
            output of ``fastboot devices``. Always ``False`` for an
            empty serial number, since an empty string is trivially a
            substring of any output.
        """
        if not self._dev_sn:
            return False
        try:
            result = subprocess.run(
                ["fastboot", "devices"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=10.0,
            )
            return self._dev_sn in result.stdout.decode(errors="replace")
        except subprocess.TimeoutExpired:
            logger.debug("fastboot: devices check timed out")
            return False
        except OSError as exc:
            logger.debug(f"fastboot: devices check failed: {exc}")
            return False

    def memdump(
        self, addr: str, size: str, output_path: "Path"
    ) -> "Optional[Path]":
        """Dump a memory region from the device to a local file.

        Executes ``fastboot oem memdump <addr> <size>`` then
        ``fastboot get_staged <output_path>``.

        :param addr: Memory start address (hex string, e.g.
            ``"0x40000000"``).
        :param size: Memory region size (hex string, e.g.
            ``"0x08000000"``).
        :param output_path: Destination file path for the dump.
        :return: *output_path* on success, ``None`` on failure.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.run(["oem", "memdump", addr, size], timeout=30.0):
            logger.warning("fastboot: oem memdump failed")
            return None

        if not self.run(["get_staged", str(output_path)], timeout=30.0):
            logger.warning("fastboot: get_staged failed")
            return None

        return output_path

    def run(self, args: List[str], timeout: float) -> bool:
        r"""Run a fastboot subcommand against :attr:`_dev_sn`.

        :param args: Arguments appended after ``fastboot -s <dev_sn>``.
        :param timeout: Maximum seconds to wait for the command.
        :return: ``True`` on exit code 0, ``False`` otherwise.
        """
        cmd = ["fastboot", "-s", self._dev_sn] + args
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            output = result.stdout.decode(errors="replace")
            logger.debug(f"fastboot {' '.join(args)}: {output.strip()}")
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.warning(f"fastboot: {' '.join(args)} timed out")
            return False
        except OSError as exc:
            logger.debug(f"fastboot: {' '.join(args)} failed: {exc}")
            return False
