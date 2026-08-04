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

"""Serial-based device implementation."""

from typing import TYPE_CHECKING, Any, Dict

import serial  # type: ignore

from ntfc.log.logger import logger

from .common import DeviceCommon

if TYPE_CHECKING:
    from ntfc.coreconfig import CoreConfig

###############################################################################
# Class: DeviceSerial
###############################################################################


class DeviceSerial(DeviceCommon):
    """This class implements host-based sim emulator."""

    def __init__(self, conf: "CoreConfig"):
        """Initialize sim emulator device."""
        DeviceCommon.__init__(self, conf, echo=False)
        self._ser = None

    def _decode_exec_args(self, args: str) -> Dict[str, Any]:
        """Decode a serial port configuration string."""
        try:
            baud, parity, data_bits, stop_bits = args.split(",")

            parity_map = {
                "n": serial.PARITY_NONE,
                "N": serial.PARITY_NONE,
                "e": serial.PARITY_EVEN,
                "E": serial.PARITY_EVEN,
                "o": serial.PARITY_ODD,
                "O": serial.PARITY_ODD,
                "m": serial.PARITY_MARK,
                "M": serial.PARITY_MARK,
                "s": serial.PARITY_SPACE,
                "S": serial.PARITY_SPACE,
            }

            bytesize_map = {
                5: serial.FIVEBITS,
                6: serial.SIXBITS,
                7: serial.SEVENBITS,
                8: serial.EIGHTBITS,
            }

            stopbits_map = {
                1: serial.STOPBITS_ONE,
                1.5: serial.STOPBITS_ONE_POINT_FIVE,
                2: serial.STOPBITS_TWO,
            }

            return {
                "baudrate": int(baud),
                "parity": parity_map.get(parity, serial.PARITY_NONE),
                "bytesize": bytesize_map.get(int(data_bits), serial.EIGHTBITS),
                "stopbits": stopbits_map.get(
                    float(stop_bits), serial.STOPBITS_ONE
                ),
            }

        except Exception as e:
            raise ValueError(f"Invalid format '{args}': {e}") from e

    def _dev_is_health_priv(self) -> bool:
        """Check if the serial device is OK."""
        if not self._ser:
            return False

        return True

    def _write(self, data: bytes) -> None:
        """Write to the serial device."""
        if not self.dev_is_health():
            return

        assert self._ser

        # send char by char to avoid line length full
        for c in data:
            self._ser.write(bytes([c]))

        # add new line if missing
        if data[-1] != ord("\n"):
            self._ser.write(b"\n")  # pragma: no cover

        # read all garbage left by character echo
        _ = self._read_all(timeout=0)
        self._console_log(_)

    def _write_ctrl(self, c: str) -> None:
        """Write a control character to the serial device."""
        if not self.dev_is_health():
            return

        assert self._ser

        code = ord(c.upper()) - 64
        self._ser.write(bytes([code]))

    def _read(self) -> bytes:
        """Read data from the serial device."""
        if not self.dev_is_health():
            return b""

        assert self._ser

        return self._ser.read(size=1024)

    def _start_impl(self) -> None:
        """Start serial communication implementation."""
        timeout = 0
        path = self._conf.exec_path
        args = self._conf.exec_args

        logger.info(f"serial path: {path}")
        logger.info(f"serial args: {args}")

        if args:  # pragma: no cover
            args = self._decode_exec_args(args)
            self._ser = serial.Serial(path, timeout=timeout, **args)
        else:
            self._ser = serial.Serial(path, timeout=timeout)

        # reboot device if possible
        self.reboot()

        ret = self._wait_for_boot(self._conf.boot_timeout)
        if ret is False:
            raise TimeoutError("device boot timeout")

    @property
    def name(self) -> str:
        """Get device name."""
        return "serial"

    @property
    def notalive(self) -> bool:
        """Check if the device is dead."""
        if not self._ser:
            return True
        return False

    def _stop_impl(self) -> None:
        """Stop serial device and close the port."""
        if self._ser:  # pragma: no cover
            self._ser.close()
            self._ser = None
        logger.info("serial device closed")

    def _poweroff_impl(self) -> bool:
        """Hardware poweroff: run the system poweroff command from config.

        :return: (bool) True on success, False if no poweroff command
         configured.
        """
        if self._conf.poweroff:  # pragma: no cover
            logger.info("poweroff core")
            self._system_cmd(self._conf.poweroff)
            self.clear_fault_flags()
            return True
        return False

    def _reboot_impl(self, timeout: int = 1) -> bool:
        """Hardware reboot: run the system reboot command from config.

        :param timeout: (int) Unused for serial devices.
        :return: (bool) True on success, False if no reboot command
         configured.
        """
        if self._conf.reboot:  # pragma: no cover
            logger.info("reboot core")
            self._system_cmd(self._conf.reboot)
            self.clear_fault_flags()
            return True
        return False
