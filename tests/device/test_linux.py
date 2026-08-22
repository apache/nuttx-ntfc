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

import pytest

from ntfc.coreconfig import CoreConfig
from ntfc.device.getos import get_os
from ntfc.device.linux import DeviceLinux
from ntfc.device.nuttx import DeviceNuttx
from ntfc.device.state import CrashType


def test_linux_shell_contract() -> None:
    device = DeviceLinux(
        CoreConfig({"name": "linux", "os": "linux", "prompt": "rtbench# "})
    )

    assert device.prompt == b"rtbench# "
    assert device.no_cmd == "not found"
    assert device.help_cmd == b"help"
    assert device.poweroff_cmd == b"poweroff"
    assert device.reboot_cmd == b"reboot"
    assert device.uname_cmd == b"uname -s"
    assert device.panic_char == ""
    assert CrashType.PANIC in device.crash_signatures


def test_get_os_defaults_to_nuttx_and_selects_linux() -> None:
    assert isinstance(get_os(CoreConfig({"name": "default"})), DeviceNuttx)
    assert isinstance(
        get_os(CoreConfig({"name": "linux", "os": "linux"})), DeviceLinux
    )


def test_get_os_rejects_unknown_operating_system() -> None:
    with pytest.raises(
        ValueError, match="unsupported operating system: plan9"
    ):
        get_os(CoreConfig({"name": "unknown", "os": "plan9"}))
