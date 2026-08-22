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

from ntfc.device.sim import DeviceSim


def test_device_sim_init():

    with patch("ntfc.coreconfig.CoreConfig") as mockdevice:
        config = mockdevice.return_value

        config.os = "nuttx"
        config.read_poll_interval = 0.1
        config.elf_path = ""
        sim = DeviceSim(config)

        assert sim.name == "sim"

        with pytest.raises(IOError):
            sim.start()


def test_device_sim_start_opens_host():
    with patch("ntfc.coreconfig.CoreConfig") as mockdevice:
        config = mockdevice.return_value
        config.os = "nuttx"
        config.read_poll_interval = 0.1
        config.elf_path = "/tmp/nuttx-sim"
        config.uptime = 3
        sim = DeviceSim(config)

        called = {}

        def fake_host_open(cmd, uptime):
            called["cmd"] = cmd
            called["uptime"] = uptime
            return None

        sim.host_open = fake_host_open
        sim.start()

        assert called["cmd"] == ["/tmp/nuttx-sim"]
        assert called["uptime"] == 3


def test_device_sim_write_adds_newline():
    with patch("ntfc.coreconfig.CoreConfig") as mockdevice:
        config = mockdevice.return_value
        config.os = "nuttx"
        config.read_poll_interval = 0.1
        config.elf_path = "/tmp/nuttx-sim"
        sim = DeviceSim(config)

        sent = []

        class FakeChild:
            def isalive(self):
                return True

            def send(self, data):
                sent.append(data)

        sim._child = FakeChild()

        sim._write(b"abc")
        assert sent[:3] == [b"a", b"b", b"c"]
        assert sent[-2:] == [b"\n", b"\n"]


def test_device_sim_write_no_extra_newline():
    with patch("ntfc.coreconfig.CoreConfig") as mockdevice:
        config = mockdevice.return_value
        config.os = "nuttx"
        config.read_poll_interval = 0.1
        config.elf_path = "/tmp/nuttx-sim"
        sim = DeviceSim(config)

        sent = []

        class FakeChild:
            def isalive(self):
                return True

            def send(self, data):
                sent.append(data)

        sim._child = FakeChild()

        sim._write(b"abc\n")
        assert sent == [b"a", b"b", b"c", b"\n"]
