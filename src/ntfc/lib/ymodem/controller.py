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

"""Ymodem transport controller."""

import subprocess
from typing import TYPE_CHECKING

from ntfc.log.logger import logger

if TYPE_CHECKING:
    from pathlib import Path


class YmodemController:
    """Transfers files from a device using the Ymodem protocol.

    Uses ``sbrb.py`` to receive a named file over a serial port.  The
    device must not hold the serial port open during :meth:`download`
    — the caller is responsible for releasing the port beforehand and
    reclaiming it afterwards.

    :param serial_port: Host-side serial port path (e.g.
        ``/dev/ttyUSB0``).
    :param sbrb_path: Path to the ``sbrb.py`` Ymodem receiver script.
    :param baud_rate: Baud rate for the serial transfer.
    """

    def __init__(
        self,
        serial_port: str,
        sbrb_path: "Path",
        baud_rate: int = 921600,
    ) -> None:
        """Initialize :class:`YmodemController`.

        :param serial_port: Host-side serial port path.
        :param sbrb_path: Path to the ``sbrb.py`` script.
        :param baud_rate: Baud rate for the Ymodem transfer.
        """
        self._serial_port = serial_port
        self._sbrb_path = sbrb_path
        self._baud_rate = baud_rate

    def is_ready(self) -> bool:
        """Return ``True`` if the controller is configured and sbrb exists.

        :return: ``True`` when *serial_port* is non-empty and the
            ``sbrb.py`` script file exists on the host.
        """
        return bool(self._serial_port) and self._sbrb_path.is_file()

    def download(self, output_dir: "Path", remote_filename: str) -> bool:
        """Transfer a named file from the device to the host via sbrb.py.

        The device's serial port must be released before calling this
        method.

        :param output_dir: Host directory where the file is saved.
        :param remote_filename: Name of the file on the device.
        :return: ``True`` on success, ``False`` on failure or timeout.
        """
        try:
            result = subprocess.run(
                [
                    str(self._sbrb_path),
                    "-r",
                    remote_filename,
                    "-t",
                    self._serial_port,
                    "-b",
                    str(self._baud_rate),
                ],
                cwd=str(output_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=3600.0,
            )
            output = result.stdout.decode(errors="replace")
            logger.debug(f"ymodem: sbrb output: {output.strip()}")
            success = "sbrb success" in output
            if not success:
                logger.warning("ymodem: sbrb did not report success")
            return success
        except subprocess.TimeoutExpired:
            logger.warning("ymodem: sbrb timed out")
            return False
        except OSError as exc:
            logger.debug(f"ymodem: sbrb launch failed: {exc}")
            return False
