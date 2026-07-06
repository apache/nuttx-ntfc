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

"""Host-based emulated devices."""

import os
import signal
import time
from typing import TYPE_CHECKING, List, Optional

import pexpect  # type: ignore
import psutil  # type: ignore

from ntfc.log.logger import logger

from .common import DeviceCommon

if TYPE_CHECKING:
    from ntfc.coreconfig import CoreConfig

###############################################################################
# Class: DeviceHost
###############################################################################


class DeviceHost(DeviceCommon):
    """This class implements common interface for host emulated devices."""

    def __init__(self, conf: "CoreConfig"):
        """Initialize host based device.

        :param conf: configuration handler
        """
        DeviceCommon.__init__(self, conf)
        self._child = None
        self._cwd = None
        self._cmd: Optional[List[str]] = None

    @property
    def pid(self) -> Optional[int]:
        """Return the spawned child PID, or ``None`` before start."""
        return self._child.pid if self._child else None

    def _dev_is_health_priv(self) -> bool:
        """Check if the host device is OK."""
        if not self._child:
            return False

        if not self._child.isalive():
            return False

        return True

    def _dev_reopen(self) -> pexpect.spawn:
        """Reopen host device."""
        if not self._cmd:
            raise ValueError("Host open command is empty")

        self._stop_impl()

        return self.host_open(self._cmd)

    def _write_ctrl(self, c: str) -> None:
        """Write a control character to the host device."""
        if not self.dev_is_health():
            return

        assert self._child
        self._child.sendcontrol(c)

    def _read(self) -> bytes:  # pragma: no cover
        """Read data from the host device."""
        if not self.dev_is_health():
            return b""

        try:
            assert self._child
            return self._child.read_nonblocking(size=5120, timeout=0)

        except (pexpect.TIMEOUT, pexpect.EOF):
            return b""

    def _kill_process_group(self, process: pexpect.spawn) -> None:
        """Kill process group."""
        pid = process.pid

        # terminate process gracefully
        os.killpg(pid, signal.SIGTERM)

        try:
            # wait for the process group to terminate
            parent = psutil.Process(pid)
            parent.wait(timeout=10)
            logger.info(f"Process group {pid} terminated successfully.")

        except psutil.TimeoutExpired:  # pragma: no cover
            logger.warning(
                f"Timeout: Process group {pid}"
                "did not terminate within 5 seconds."
            )
            # force termination
            os.killpg(pid, signal.SIGKILL)
            logger.info(f"Sent SIGKILL to process group {pid}")

        self._child = None

    def host_open(self, cmd: List[str], uptime: int = 0) -> pexpect.spawn:
        """Open host-based target device."""
        if self._child:
            raise IOError("Host device already open")

        self._child = None
        self.clear_fault_flags()

        # we need command to reopen file in the case of crash
        self._cmd = cmd

        logger.info(f"spawn cmd: {''.join(cmd)}")
        self._child = pexpect.spawn(
            "".join(cmd), timeout=10, maxread=20000, cwd=self._cwd
        )

        time.sleep(uptime)

        ret = self._wait_for_boot()
        if ret is False:  # pragma: no cover
            raise TimeoutError("device boot timeout")

        return self._child

    def _stop_impl(self) -> None:
        """Stop host device and kill the underlying process."""
        if not self._child:
            return

        if self._child.isalive():  # pragma: no cover
            # send power off via software (OS command) to avoid recursion
            self.poweroff(hard=False)
            time.sleep(1)

        if self._child.isalive():  # pragma: no cover
            # kill process group
            self._kill_process_group(self._child)

        self._child = None

        logger.info("host device closed")

    @property
    def name(self) -> str:
        """Get device name."""
        return "host_unknown"

    @property
    def notalive(self) -> bool:
        """Check if the device is dead."""
        if not self._child:
            return True
        return not self._child.isalive()

    def _poweroff_impl(self) -> bool:
        """Hardware poweroff: restart the host process via ``_dev_reopen``.

        :return: (bool) True on success, False otherwise.
        """
        return bool(self._dev_reopen())

    def _reboot_impl(self, timeout: int) -> bool:
        """Hardware reboot: restart the host process via ``_dev_reopen``.

        :param timeout: (int) Unused for host devices.
        :return: (bool) True on success, False otherwise.
        """
        del timeout
        return bool(self._dev_reopen())
