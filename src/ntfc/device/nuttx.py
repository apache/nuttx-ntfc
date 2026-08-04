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

"""NuttX target device implementation."""

from typing import TYPE_CHECKING, Dict, List

from ntfc.device.state import CrashType

from .oscommon import OSCommon

if TYPE_CHECKING:
    from ntfc.coreconfig import CoreConfig

###############################################################################
# Class: DeviceNuttx
###############################################################################


class DeviceNuttx(OSCommon):
    """This class implements NuttX target device."""

    _PROMPT = b"nsh>"
    _NO_CMD = "command not found"
    _HELP_CMD = b"help"
    _POWEROFF_CMD = b"poweroff"
    _REBOOT_CMD = b"reboot"
    _UNAME_CMD = b"uname -o"
    _UNAME_RESP = b"NuttX"
    _CRASH_SIGNATURES: Dict[CrashType, List[bytes]] = {
        CrashType.ASSERTION: [
            b"Assertion failed",
            b"Reset board on recursive assert",
            b"up_dump_register",
            b"dump_tasks",
        ],
        # kernel-mode (CONFIG_BUILD_KERNEL) user task faults: the kernel
        # kills the offending task and keeps running, so the console
        # message is the only crash evidence
        CrashType.SEGFAULT: [
            b"Segmentation fault in",
            b"PANIC: Unhandled user exception",
        ],
    }
    _PANIC_CHAR = r"/"

    def __init__(self, conf: "CoreConfig"):
        """Initialize NuttX OS abstraction."""
        self._conf = conf

        # custom prompt
        self._prompt = conf.prompt.encode() if conf.prompt else self._PROMPT

        # TODO: login, password etc

    @property
    def prompt(self) -> bytes:
        """Get prompt."""
        return self._prompt

    @property
    def no_cmd(self) -> str:
        """Get command not found string."""
        return self._NO_CMD

    @property
    def help_cmd(self) -> bytes:
        """Get help command."""
        return self._HELP_CMD

    @property
    def poweroff_cmd(self) -> bytes:
        """Get poweroff command."""
        return self._POWEROFF_CMD

    @property
    def reboot_cmd(self) -> bytes:
        """Get reboot command."""
        return self._REBOOT_CMD

    @property
    def uname_cmd(self) -> bytes:
        """Get uname command."""
        return self._UNAME_CMD

    @property
    def crash_signatures(self) -> Dict[CrashType, List[bytes]]:
        """Get crash signatures grouped by crash type."""
        return self._CRASH_SIGNATURES

    @property
    def panic_char(self) -> str:
        """Get force panic character."""
        ch = self._conf.kv_check("CONFIG_TTY_FORCE_PANIC_CHAR")
        if not ch:
            return ""
        return chr(ch + 0x1F)
