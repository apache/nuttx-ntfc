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

"""Device whose only console is a NuttX netdev console (real hardware)."""

from typing import TYPE_CHECKING

from ntfc.log.logger import logger

from .common import DeviceCommon
from .netconsole import NetConsole, get_netconsole

if TYPE_CHECKING:
    from ntfc.coreconfig import CoreConfig

###############################################################################
# Class: DeviceNetdev
###############################################################################


class DeviceNetdev(DeviceCommon):
    """Target reached only through its netdev console.

    This is the device for real hardware built with CONFIG_CONSOLE_NETDEV:
    NTFC does not spawn anything, it talks to the board over the transport
    of the ``netconsole`` section. The board is reset and powered off with
    the ``reboot`` and ``poweroff`` system commands of the configuration,
    as for a serial device. The transport is started before the reset so
    the boot output, which also gives NTFC the UDP target address, is not
    lost.
    """

    def __init__(self, conf: "CoreConfig"):
        """Initialize the netdev console device.

        :param conf: configuration handler
        """
        DeviceCommon.__init__(self, conf, echo=False)
        con = get_netconsole(conf.netconsole)
        if con is None:
            raise ValueError("netdev device needs a netconsole section")
        self._con: NetConsole = con

    @property
    def name(self) -> str:
        """Get device name."""
        return "netdev"

    @property
    def notalive(self) -> bool:
        """Check if the device is dead."""
        return not self._con.is_open

    def _dev_is_health_priv(self) -> bool:
        """Check if the console transport is open."""
        return self._con.is_open

    def _write(self, data: bytes) -> None:
        """Write a command to the console."""
        if not self.dev_is_health():
            return

        if data[-1] != ord("\n"):
            data += b"\n"

        self._con.write(data)

    def _write_ctrl(self, c: str) -> None:
        """Write a control character to the console."""
        if not self.dev_is_health():
            return

        self._con.write(bytes([ord(c.upper()) & 0x1F]))

    def _read(self) -> bytes:
        """Read console data."""
        if not self.dev_is_health():
            return b""

        return self._con.read()

    def _start_impl(self) -> None:
        """Start the transport, reset the board and wait for the prompt."""
        self._con.start()
        self.reboot()
        ret = self._wait_for_boot(self._conf.boot_timeout)
        if ret is False:
            raise TimeoutError("device boot timeout")

    def _stop_impl(self) -> None:
        """Stop the console transport."""
        self._con.stop()
        logger.info("netdev device closed")

    def _poweroff_impl(self) -> bool:
        """Hardware poweroff: run the poweroff command from config.

        :return: (bool) True on success, False if no poweroff command
         configured.
        """
        if self._conf.poweroff:
            logger.info("poweroff core")
            self._system_cmd(self._conf.poweroff)
            self.clear_fault_flags()
            return True
        return False

    def _reboot_impl(self, timeout: int = 1) -> bool:
        """Hardware reboot: run the reboot command from config.

        :param timeout: (int) Unused for netdev devices.
        :return: (bool) True on success, False if no reboot command
         configured.
        """
        del timeout
        if self._conf.reboot:
            logger.info("reboot core")
            self._system_cmd(self._conf.reboot)
            self.clear_fault_flags()
            return True
        return False
