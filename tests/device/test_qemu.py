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

import pytest

from ntfc.device.qemu import DeviceQemu


def test_device_qemu_open():

    with patch("ntfc.coreconfig.CoreConfig") as mockdevice:
        config = mockdevice.return_value

        config.os = "nuttx"
        config.read_poll_interval = 0.1
        config.exec_path = ""
        config.exec_args = ""
        config.elf_path = ""

        qemu = DeviceQemu(config)

        with pytest.raises(IOError):
            qemu.start()

        config.exec_path = ""
        config.exec_args = ""
        config.elf_path = "some/path"

        with pytest.raises(KeyError):
            qemu.start()

        assert qemu.name == "qemu"

        def host_open_dummy1(cmd, uptime):
            assert uptime == 3
            assert cmd == [
                "some/path",
                " ",
                "-kernel some/image",
                " ",
                "some args",
            ]

        qemu.host_open = host_open_dummy1

        config.exec_path = "some/path"
        config.exec_args = "some args"
        config.elf_path = "some/image"
        config.uptime = 3

        qemu.start()

        def host_open_dummy2(cmd, uptime):
            assert uptime == 3
            assert cmd == [
                "some/path",
                " ",
                "-bios some/image",
            ]

        qemu.host_open = host_open_dummy2

        config.exec_path = "some/path"
        config.exec_args = "-bios $IMAGE_ELF"
        config.elf_path = "some/image"
        config.uptime = 3

        qemu.start()

        def host_open_dummy3(cmd, uptime):
            print(cmd)
            assert uptime == 3
            assert cmd == [
                "some/path",
                " ",
                "some/image -params",
            ]

        qemu.host_open = host_open_dummy3

        config.exec_path = "some/path"
        config.exec_args = "$IMAGE_ELF -params"
        config.elf_path = "some/image"
        config.uptime = 3

        qemu.start()

        def host_open_dummy4(cmd, uptime):
            print(cmd)
            assert uptime == 3
            assert cmd == [
                "some/path",
                " ",
                "-kernel custom/img",
            ]

        qemu.host_open = host_open_dummy4

        config.exec_path = "some/path"
        config.exec_args = "-kernel custom/img"
        config.elf_path = "some/image"
        config.uptime = 3

        qemu.start()
