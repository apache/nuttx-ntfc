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

import re
from unittest.mock import ANY, MagicMock, patch

import pytest

from ntfc.core import CoreStatus, ProductCore
from ntfc.device.common import CmdReturn, CmdStatus
from ntfc.envconfig import EnvConfig


def test_core_init(envconfig_dummy):

    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value

        with pytest.raises(TypeError):
            _ = ProductCore(None, envconfig_dummy.product[0].cfg_core(0))

        with pytest.raises(TypeError):
            _ = ProductCore(dev, None)

        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        p.init()

        assert p.__str__() == "ProductCore: dummy"
        assert p.cores == ("core0",)
        assert p.device is not None
        assert p.prompt is not None
        assert p.conf is not None


def test_core_internals(envconfig_dummy):

    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        dev.no_cmd = "command not found"

        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        assert p._match_not_found(None) is False
        a = re.match(rb"test", b"nsh>")
        assert p._match_not_found(a) is False
        b = re.match(rb"command not found", b"command not found")
        assert p._match_not_found(b) is True


def test_core_send_command(envconfig_dummy):

    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        dev.prompt = b"NSH> "
        dev.no_cmd = "command not found"
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.TIMEOUT
        )
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        # empty command
        with pytest.raises(ValueError):
            p.sendCommand(None)

        # should work with or without /n
        # pass retcode from send_cmd_read_until_pattern
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS
        )
        assert p.sendCommand("test\n") == CmdStatus.SUCCESS
        assert p.sendCommand("test") == CmdStatus.SUCCESS
        assert p.sendCommand("test", "") == CmdStatus.SUCCESS

        # timeout
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.TIMEOUT
        )
        assert p.sendCommand("test\n") == CmdStatus.TIMEOUT

        # command not found
        tmp = re.compile("command not found", 0).search("command not found")
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS, tmp
        )
        assert p.sendCommand("test") == CmdStatus.NOTFOUND


def test_core_rejects_command_longer_than_line_max(config_sim):
    """A command the shell cannot buffer is refused instead of split."""

    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        dev.prompt = b"NSH> "
        dev.no_cmd = "command not found"
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS
        )
        core = EnvConfig(config_sim).product[0].cfg_core(0)
        assert core.kv_check("CONFIG_LINE_MAX") == 80
        p = ProductCore(dev, core)

        assert p.sendCommand("x" * 79) == CmdStatus.SUCCESS
        with pytest.raises(ValueError, match="CONFIG_LINE_MAX"):
            p.sendCommand("x" * 80)
        with pytest.raises(ValueError, match="CONFIG_LINE_MAX"):
            p.sendCommandReadUntilPattern("x" * 70, args=["y" * 10])


def test_core_line_max_unknown_is_not_checked(envconfig_dummy):

    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        dev.prompt = b"NSH> "
        dev.no_cmd = "command not found"
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS
        )
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))
        assert p.sendCommand("x" * 500) == CmdStatus.SUCCESS


def test_core_send_command_read_until_pattern(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        dev._main_prompt = "nsh>"
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        with pytest.raises(ValueError):
            p.sendCommandReadUntilPattern("")

        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.NOTFOUND
        )
        assert p.sendCommandReadUntilPattern("test", "test") == CmdReturn(
            CmdStatus.NOTFOUND
        )

        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS
        )
        assert p.sendCommandReadUntilPattern("test", "test") == CmdReturn(
            CmdStatus.SUCCESS
        )


def test_core_read_until_pattern(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        # success: device returns SUCCESS
        dev.read_until_pattern.return_value = CmdReturn(CmdStatus.SUCCESS)
        assert p.readUntilPattern("PASS") == CmdReturn(CmdStatus.SUCCESS)

        # fail_pattern triggered: device returns FAILED
        dev.read_until_pattern.return_value = CmdReturn(CmdStatus.FAILED)
        assert p.readUntilPattern("PASS", fail_pattern="FAIL") == CmdReturn(
            CmdStatus.FAILED
        )

        # encoded pattern and fail_pattern passed correctly
        p.readUntilPattern("PASS", timeout=10, fail_pattern="FAIL")
        dev.read_until_pattern.assert_called_with(
            pattern=b"PASS", timeout=10, fail_pattern=b"(?:FAIL)"
        )

        # bytes pattern
        p.readUntilPattern(b"PASS", timeout=5)
        dev.read_until_pattern.assert_called_with(
            pattern=b"PASS", timeout=5, fail_pattern=None
        )

        # list of patterns concatenated (encode_for_device behavior)
        p.readUntilPattern(["OK", b"DONE"], timeout=15)
        dev.read_until_pattern.assert_called_with(
            pattern=b"OKDONE", timeout=15, fail_pattern=None
        )

        # list fail_pattern OR-joined
        p.readUntilPattern("PASS", fail_pattern=["FAIL", b"ERROR"])
        dev.read_until_pattern.assert_called_with(
            pattern=ANY, timeout=30, fail_pattern=b"(?:FAIL)|(?:ERROR)"
        )


def test_core_send_command_fail_pattern(envconfig_dummy):

    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        dev.prompt = b"NSH> "
        dev.no_cmd = "command not found"
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS
        )
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        # no fail_pattern: device called without fail_pattern kwarg
        p.sendCommand("test")
        dev.send_cmd_read_until_pattern.assert_called_with(
            b"test", pattern=ANY, timeout=30, fail_pattern=None
        )

        # literal string: encoded as escaped bytes regex
        p.sendCommand("test", fail_pattern="ERROR")
        dev.send_cmd_read_until_pattern.assert_called_with(
            b"test", pattern=ANY, timeout=30, fail_pattern=b"(?:ERROR)"
        )

        # list of literals
        p.sendCommand("test", fail_pattern=["ERR", "PANIC"])
        dev.send_cmd_read_until_pattern.assert_called_with(
            b"test",
            pattern=ANY,
            timeout=30,
            fail_pattern=b"(?:ERR)|(?:PANIC)",
        )

        # regexp=True: patterns passed as-is (not escaped)
        p.sendCommand("test", fail_pattern=r"err\d+", regexp=True)
        dev.send_cmd_read_until_pattern.assert_called_with(
            b"test",
            pattern=ANY,
            timeout=30,
            fail_pattern=rb"(?:err\d+)",
        )

        # device returns FAILED → propagated as-is
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.FAILED
        )
        assert p.sendCommand("test", fail_pattern="ERROR") == CmdStatus.FAILED

        # device returns SUCCESS without fail_pattern → SUCCESS
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS
        )
        assert p.sendCommand("test", fail_pattern="ERROR") == CmdStatus.SUCCESS


def test_core_send_command_read_until_pattern_fail_pattern(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        dev._main_prompt = "nsh>"
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS
        )
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        # no fail_pattern: device called with fail_pattern=None
        p.sendCommandReadUntilPattern("test", "test")
        dev.send_cmd_read_until_pattern.assert_called_with(
            b"test", pattern=b"test", timeout=30, fail_pattern=None
        )

        # str fail_pattern encoded to bytes
        p.sendCommandReadUntilPattern("test", "test", fail_pattern="ERROR")
        dev.send_cmd_read_until_pattern.assert_called_with(
            b"test", pattern=b"test", timeout=30, fail_pattern=b"(?:ERROR)"
        )

        # bytes fail_pattern
        p.sendCommandReadUntilPattern("test", "test", fail_pattern=b"PANIC")
        dev.send_cmd_read_until_pattern.assert_called_with(
            b"test", pattern=b"test", timeout=30, fail_pattern=b"(?:PANIC)"
        )

        # list of str/bytes OR-joined
        p.sendCommandReadUntilPattern(
            "test", "test", fail_pattern=["ERR", b"CRASH"]
        )
        dev.send_cmd_read_until_pattern.assert_called_with(
            b"test",
            pattern=b"test",
            timeout=30,
            fail_pattern=b"(?:ERR)|(?:CRASH)",
        )

        # device returns FAILED → returned as-is
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.FAILED
        )
        result = p.sendCommandReadUntilPattern(
            "test", "test", fail_pattern="ERROR"
        )
        assert result.status == CmdStatus.FAILED


def test_core_send_ctrl_cmd(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        with pytest.raises(ValueError):
            p.sendCtrlCmd("")

        with pytest.raises(ValueError):
            p.sendCtrlCmd("aaa")

        dev.send_ctrl_cmd.return_value = CmdStatus.TIMEOUT
        assert p.sendCtrlCmd("a") is None

        dev.send_ctrl_cmd.return_value = CmdStatus.SUCCESS
        assert p.sendCtrlCmd("a") is None


def test_core_reboot(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        dev.reboot.return_value = False
        assert p.reboot() is False

        dev.reboot.return_value = True
        assert p.reboot() is True


def test_core_force_panic(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        dev.panic_char = ""
        assert p.force_panic() is False

        dev.panic_char = "X"
        dev.send_ctrl_cmd.return_value = CmdStatus.TIMEOUT
        assert p.force_panic() is False

        dev.send_ctrl_cmd.return_value = CmdStatus.SUCCESS
        assert p.force_panic() is True
        dev.send_ctrl_cmd.assert_called_with("X")

        dev.send_ctrl_cmd.return_value = True
        assert p.force_panic() is True


def test_core_busyloop(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        dev.busyloop = False
        assert p.busyloop is False
        dev.busyloop = True
        assert p.busyloop is True


def test_core_crash(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        dev.crash = False
        assert p.crash is False
        dev.crash = True
        assert p.crash is True


def test_core_notalive(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        dev.notalive = False
        assert p.notalive is False
        dev.notalive = True
        assert p.notalive is True


def test_core_status_checker(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        dev.busyloop = False
        dev.crash = False
        dev.flood = False
        dev.notalive = False
        assert p.status == CoreStatus.NORMAL

        dev.busyloop = True
        dev.crash = False
        dev.flood = False
        dev.notalive = False
        assert p.status == CoreStatus.BUSYLOOP

        dev.busyloop = False
        dev.crash = True
        dev.flood = False
        dev.notalive = False
        assert p.status == CoreStatus.CRASH

        dev.busyloop = False
        dev.crash = False
        dev.flood = True
        dev.notalive = False
        assert p.status == CoreStatus.FLOOD

        dev.busyloop = False
        dev.crash = False
        dev.flood = False
        dev.notalive = True
        assert p.status == CoreStatus.NOTALIVE


def test_core_get_core_info(envconfig_dummy):

    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.TIMEOUT
        )

        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        assert p.cur_core is None

        # send_cmd_read_until_pattern failed
        assert p.get_core_info() == ()

        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS, None, "xxx"
        )
        assert p.get_core_info() == ()
        assert p.cur_core is None

        dev.prompt = b"dummy"
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS,
            None,
            "Local CPU Remote CPU\n",
        )
        assert p.get_core_info() == ()
        assert p.cur_core is None

        dev.prompt = b"dummy"
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS,
            None,
            "Local CPU Remote CPU\n0 1",
        )
        assert p.get_core_info() == ("0", "1")
        assert p.cur_core is None

        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS,
            None,
            "Local CPU Remote CPU\n2 3",
        )
        assert p.get_core_info() == ("2", "3")
        assert p.cur_core is None

        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS,
            None,
            "Local CPU Remote CPU\n2 3",
        )
        assert p.get_core_info() == ("2", "3")
        assert p.cur_core is None

        p.init()
        assert p.cur_core == "2"


def test_core_switch_core(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        dev.no_cmd = ""
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        with pytest.raises(ValueError):
            p.switch_core("")

        p.init()

        assert p.switch_core("") == -1

        p._core0 = "AAA"
        assert p.switch_core("aaa") == 0

        p._core0 = "bbb"
        p._cores = ["bbb", "ccc"]
        assert p.switch_core("aaa") == -1

        p._core0 = "bbb"
        p._cores = ["bbb", "ccc"]
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.NOTFOUND
        )
        assert p.switch_core("ccc") == CmdStatus.NOTFOUND
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS
        )
        assert p.switch_core("ccc") == CmdStatus.SUCCESS


def test_core_get_current_prompt(envconfig_dummy):
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.NOTFOUND
        )
        assert p.get_current_prompt() == ">"

        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS, re.match(rb"(\S+)>", b"nsh>")
        )
        assert p.get_current_prompt() == "nsh>"


def test_core_check_cmd_without_elf_parser(envconfig_dummy):
    """Test check_cmd fallback when ELF parser is not available."""
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        # Set required attributes (but NOT elf_parser)
        dev.prompt = b"nsh>"
        dev.no_cmd = "command not found"
        # IMPORTANT: Explicitly set elf_parser to None to prevent MagicMock
        # from auto-creating it as a truthy attribute
        dev.elf_parser = None

        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        # Mock send_cmd_read_until_pattern for help command
        # Note: ProductCore.sendCommandReadUntilPattern calls
        # dev.send_cmd_read_until_pattern
        help_output = "Available commands: free ps\n"
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS, None, help_output
        )

        # Test command found in help output
        assert p.check_cmd("free") is True

        # Reset the mock for next call
        dev.send_cmd_read_until_pattern.reset_mock()
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS, None, help_output
        )
        assert p.check_cmd("free|ps") is True

        # Reset the mock for next call
        dev.send_cmd_read_until_pattern.reset_mock()
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS, None, help_output
        )
        assert p.check_cmd("ps") is True

        # Reset the mock for next call
        dev.send_cmd_read_until_pattern.reset_mock()
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.SUCCESS, None, help_output
        )

        # Test command not found in help output
        assert p.check_cmd("nonexistent") is False

        # Test with failed help command
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.TIMEOUT
        )
        assert p.check_cmd("test") is False


def test_core_check_cmd_with_elf_parser(envconfig_dummy):
    """Test check_cmd with ELF parser available."""
    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        dev = mockdevice.return_value
        dev.prompt = b"nsh>"
        dev.no_cmd = "command not found"

        # Create a mock ELF parser
        mock_elf_parser = MagicMock()
        mock_elf_parser.has_symbol.return_value = False

        # Set elf_parser on the device
        dev.elf_parser = mock_elf_parser

        p = ProductCore(dev, envconfig_dummy.product[0].cfg_core(0))

        # Test command not found
        assert p.check_cmd("free") is False
        mock_elf_parser.has_symbol.assert_called_with("free")

        # Test command found
        mock_elf_parser.has_symbol.return_value = True
        assert p.check_cmd("ps") is True
        mock_elf_parser.has_symbol.assert_called_with("ps")

        # Test cmocka pattern (should append _main)
        mock_elf_parser.has_symbol.return_value = True
        assert p.check_cmd("test_cmocka") is True
        mock_elf_parser.has_symbol.assert_called_with("test_cmocka_main")

        # Test alternatives with pipe
        mock_elf_parser.has_symbol.side_effect = [False, True]
        assert p.check_cmd("test1|test2") is True

        # Test regex wildcard pattern
        mock_elf_parser.has_symbol.side_effect = None
        mock_elf_parser.has_symbol.return_value = True
        assert p.check_cmd("test.*") is True
        # The pattern should be compiled as regex
        call_args = mock_elf_parser.has_symbol.call_args
        assert isinstance(call_args[0][0], re.Pattern)

        # Test all alternatives not found
        mock_elf_parser.has_symbol.return_value = False
        assert p.check_cmd("nonexistent1|nonexistent2") is False

        # Test with failed help command
        dev.send_cmd_read_until_pattern.return_value = CmdReturn(
            CmdStatus.TIMEOUT
        )
        assert p.check_cmd("test") is False


def test_core_check_cmd_kernel_mode(tmp_path):
    """Test check_cmd resolves via app_bindir on kernel builds."""
    from ntfc.coreconfig import CoreConfig

    kernel_cfg = tmp_path / "kv_config"
    kernel_cfg.write_text("CONFIG_BUILD_KERNEL=y\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "hello").write_bytes(b"\x7fELF" + b"\x00" * 12)

    conf = CoreConfig(
        {
            "name": "t",
            "conf_path": str(kernel_cfg),
            "app_bindir": str(bindir),
        }
    )

    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        p = ProductCore(mockdevice.return_value, conf)

        # resolved from the application directory, device is not queried
        assert p.check_cmd("hello") is True
        assert p.check_cmd("hello_main") is True
        assert p.check_cmd("nonexistent") is False
        mockdevice.return_value.send_cmd_read_until_pattern.assert_not_called()


def test_core_check_cmd_kernel_runtime_fallback(tmp_path, monkeypatch):
    """Test check_cmd discovers commands from the running target."""
    from ntfc.coreconfig import CoreConfig

    kernel_cfg = tmp_path / "kv_config"
    kernel_cfg.write_text(
        'CONFIG_BUILD_KERNEL=y\nCONFIG_PATH_INITIAL="/system/bin"\n'
    )
    # a kernel core whose application binaries are not on the host:
    # the command set has to come from the running target
    conf = CoreConfig(
        {
            "name": "t",
            "conf_path": str(kernel_cfg),
            "elf_path": "./tests/resources/nuttx/sim/nuttx",
        }
    )
    assert conf.has_app_bindir is False

    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        p = ProductCore(mockdevice.return_value, conf)

        calls = []
        status = [CmdStatus.TIMEOUT]

        def fake_send(cmd, pattern=None, args=None, timeout=30):
            calls.append(cmd)
            output = "ls /system/bin\n/system/bin:\n hello\n init\n sh\nnsh> "
            return CmdReturn(status[0], output=output)

        monkeypatch.setattr(p, "sendCommandReadUntilPattern", fake_send)

        # listing failure is not cached
        assert p.check_cmd("hello") is False
        assert len(calls) == 1

        status[0] = CmdStatus.SUCCESS
        assert p.check_cmd("hello") is True
        assert p.check_cmd("hello_main") is True
        assert p.check_cmd("missing|sh") is True
        assert p.check_cmd("missing") is False

        # target was listed once after the failed attempt
        assert calls == ["ls /system/bin", "ls /system/bin"]


def test_core_check_cmd_kernel_runtime_does_not_cache_ls_error(
    tmp_path, monkeypatch
):
    """Do not interpret words from an ls error as target commands."""
    from ntfc.coreconfig import CoreConfig

    kernel_cfg = tmp_path / "kv_config"
    kernel_cfg.write_text("CONFIG_BUILD_KERNEL=y\n")
    conf = CoreConfig({"name": "t", "conf_path": str(kernel_cfg)})

    with patch("ntfc.device.common.DeviceCommon") as mockdevice:
        p = ProductCore(mockdevice.return_value, conf)
        calls = []

        def fake_send(cmd, pattern=None, args=None, timeout=30):
            calls.append(cmd)
            return CmdReturn(
                CmdStatus.SUCCESS,
                output=(
                    "ls /system/bin\n"
                    "ls: /system/bin: No such file or directory\n"
                    "nsh> "
                ),
            )

        monkeypatch.setattr(p, "sendCommandReadUntilPattern", fake_send)

        assert p.check_cmd("No") is False
        assert p.check_cmd("file") is False
        assert calls == ["ls /system/bin", "ls /system/bin"]
