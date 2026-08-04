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

from unittest.mock import patch

from ntfc.device.nuttx import DeviceNuttx
from ntfc.device.state import CrashType


def test_device_nuttx_init():

    with patch("ntfc.envconfig.EnvConfig") as mockdevice:
        config = mockdevice.return_value

        d = DeviceNuttx(config)
        assert d is not None

        assert d.prompt is not None
        assert d.no_cmd is not None
        assert d.help_cmd is not None
        assert d.poweroff_cmd is not None
        assert d.reboot_cmd is not None
        assert d.uname_cmd is not None

        sigs = d.crash_signatures
        assert CrashType.ASSERTION in sigs
        assert all(isinstance(v, list) for v in sigs.values())

        # kernel-mode user task faults kill only the task; the console
        # message is the only crash evidence
        assert CrashType.SEGFAULT in sigs
        assert b"Segmentation fault in" in sigs[CrashType.SEGFAULT]
        assert b"PANIC: Unhandled user exception" in sigs[CrashType.SEGFAULT]

        # real rv-virt knsh64 console output is classified as SEGFAULT
        from ntfc.device.state import DeviceStateManager

        mgr = DeviceStateManager(crash_signatures=sigs)
        line = (
            b"[    2.966000] riscv_fault_handler: "
            b"Segmentation fault in getprime (PID 4: getprime)"
        )
        assert mgr._detect_crash_type(line) is CrashType.SEGFAULT

        config.kv_check.return_value = 0
        assert d.panic_char == ""
        config.kv_check.return_value = 1
        assert d.panic_char == chr(0x20)
