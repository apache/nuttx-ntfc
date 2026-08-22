############################################################################
# SPDX-License-Identifier: Apache-2.0
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.  The
# ASF licenses this file to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
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

"""Linux shell abstraction for serial and QEMU test devices."""

from typing import TYPE_CHECKING, Dict, List

from ntfc.device.state import CrashType

from .oscommon import OSCommon

if TYPE_CHECKING:
    from ntfc.coreconfig import CoreConfig


class DeviceLinux(OSCommon):
    """Describe the Linux shell contract used by NTFC devices."""

    _PROMPT = b"#"
    _CRASH_SIGNATURES: Dict[CrashType, List[bytes]] = {
        CrashType.PANIC: [
            b"Kernel panic - not syncing",
            b"not syncing: Fatal exception",
        ],
        CrashType.ASSERTION: [b"BUG: unable to handle kernel"],
    }

    def __init__(self, conf: "CoreConfig") -> None:
        """Initialize the Linux shell abstraction."""
        self._prompt = conf.prompt.encode() if conf.prompt else self._PROMPT

    @property
    def prompt(self) -> bytes:
        """Get shell prompt."""
        return self._prompt

    @property
    def no_cmd(self) -> str:
        """Get command-not-found marker."""
        return "not found"

    @property
    def help_cmd(self) -> bytes:
        """Get shell help command."""
        return b"help"

    @property
    def poweroff_cmd(self) -> bytes:
        """Get shell poweroff command."""
        return b"poweroff"

    @property
    def reboot_cmd(self) -> bytes:
        """Get shell reboot command."""
        return b"reboot"

    @property
    def uname_cmd(self) -> bytes:
        """Get operating-system identification command."""
        return b"uname -s"

    @property
    def crash_signatures(self) -> Dict[CrashType, List[bytes]]:
        """Get Linux kernel crash signatures."""
        return self._CRASH_SIGNATURES

    @property
    def panic_char(self) -> str:
        """Linux does not define a console panic character here."""
        return ""
