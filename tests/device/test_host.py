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

from unittest.mock import MagicMock

import pytest
from pexpect.exceptions import ExceptionPexpect

from ntfc.device.host import DeviceHost


# need to define start which is specific for device implementation
class DeviceHost2(DeviceHost):
    def _start_impl(self):
        pass

    def _write(self, data):
        if not self.dev_is_health():
            return

        assert self._child
        # send char by char to avoid line length full
        for c in data:
            self._child.send(bytes([c]))

        # add new line if missing
        if data[-1] != ord("\n"):
            # sometimes new line send to sim is missing
            # so we have to send more than one new line
            self._child.send(b"\n\n")


def test_device_host_open(envconfig_dummy, monkeypatch):

    conf = envconfig_dummy.product[0].cfg_core(0)
    path = "./tests/resources/nuttx/sim/nuttx"
    dev = DeviceHost2(conf)

    assert dev.name == "host_unknown"
    assert dev._dev_is_health_priv() is False

    # stop on non-started device is a no-op
    dev.stop()

    with pytest.raises(ValueError):
        _ = dev._dev_reopen()

    assert dev.notalive is True

    with pytest.raises(ExceptionPexpect):
        dev.host_open(["dummyxxxx"])

    assert dev.notalive is True

    with pytest.raises(ExceptionPexpect):
        _ = dev._dev_reopen()

    # open executable
    assert dev.host_open([path]) is not None

    with pytest.raises(IOError):
        dev.host_open([path])

    assert dev.notalive is False
    assert dev._dev_is_health_priv() is True
    assert dev._write(b"a") is None
    assert dev._write(b"a\n") is None

    # reopen
    assert dev._dev_reopen() is not None

    # hard poweroff/reboot: restart host process -> True
    assert dev.poweroff() is True
    assert dev.reboot(1) is True

    # soft reboot: patch _wait_for_boot since sim restart timing is
    # non-deterministic; the real boot wait is tested separately
    monkeypatch.setattr(dev, "_wait_for_boot", lambda t=5: True)
    assert dev.reboot(1, hard=False) is True
    monkeypatch.undo()

    # soft poweroff: sends OS command, no boot wait required
    assert dev.poweroff(hard=False) is True

    # stop device
    dev.stop()
    assert dev.notalive is True
    assert dev._dev_is_health_priv() is False
    assert dev._write(b"a") is None
    assert dev._write_ctrl("a") is None

    # open executable
    ret = dev.host_open([path])
    assert ret is not None
    assert dev.notalive is False

    def dummy(hard: bool = True) -> bool:
        return True

    dev.poweroff = dummy
    dev.stop()
    assert dev.notalive is True

    dev.start()


def test_device_host_command(envconfig_dummy):

    conf = envconfig_dummy.product[0].cfg_core(0)
    path = "./tests/resources/nuttx/sim/nuttx"
    dev = DeviceHost2(conf)

    assert dev.no_cmd is not None

    # open executable
    ret = dev.host_open([path])
    assert ret is not None
    assert dev.notalive is False

    # check hello world command in bytes
    ret = dev.send_command(b"hello", 1)
    assert b"Hello, World!" in ret

    # check hello world command in string
    ret = dev.send_command("hello", 1)
    assert b"Hello, World!" in ret

    # no pattern in output
    ret = dev.send_cmd_read_until_pattern(b"hello", b"dummy", 1)
    assert ret.status == -2

    # pattern in output
    ret = dev.send_cmd_read_until_pattern(b"hello", b"Hello", 1)
    assert ret.status == 0

    # pattern in output
    ret = dev.send_cmd_read_until_pattern(b"hello", b"World!", 1)
    assert ret.status == 0

    # pattern in output
    ret = dev.send_cmd_read_until_pattern(b"hello", b"Hello, World!", 1)
    assert ret.status == 0

    with pytest.raises(TypeError):
        _ = dev.send_cmd_read_until_pattern("hello", "Hello, World!", 1)

    with pytest.raises(TypeError):
        _ = dev.send_cmd_read_until_pattern(b"hello", "Hello, World!", 1)

    assert dev.send_ctrl_cmd("Z") == 0


def test_device_host_reboot_failure(envconfig_dummy, monkeypatch):

    conf = envconfig_dummy.product[0].cfg_core(0)
    dev = DeviceHost2(conf)

    monkeypatch.setattr(dev, "_dev_reopen", lambda: None)
    assert dev.reboot(1) is False


def test_device_host_reboot_boot_wait_failure(envconfig_dummy, monkeypatch):

    conf = envconfig_dummy.product[0].cfg_core(0)
    dev = DeviceHost2(conf)

    # hard: _dev_reopen succeeds but device never comes back up
    monkeypatch.setattr(dev, "_dev_reopen", lambda: object())
    monkeypatch.setattr(dev, "_wait_for_boot", lambda t=5: False)
    assert dev.reboot(1) is False

    # soft: command sent but device never comes back up
    assert dev.reboot(1, hard=False) is False


def test_device_host_pid(envconfig_dummy):

    conf = envconfig_dummy.product[0].cfg_core(0)
    dev = DeviceHost2(conf)

    assert dev.pid is None

    dev._child = MagicMock()
    dev._child.pid = 4242
    assert dev.pid == 4242


# TODO: more tests for host device !!!!
#   - test for timeout
#   - test for very long output
#   - test for
