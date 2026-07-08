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

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    import pytest

from ntfc.debug.config import DebugConfig
from ntfc.debug.getdebug import DebugSetup, get_debug_setup
from ntfc.pytest.coredump_plugin import CoredumpPlugin


def _make_product(
    name: str = "prod",
    debug: Optional[Dict[str, Any]] = None,
    elf: str = "",
    cores_num: int = 1,
) -> MagicMock:
    p = MagicMock()
    p.name = name
    p.conf.debug = DebugConfig(debug or {})
    p.conf.cfg_core.return_value.elf_path = elf
    p.conf.cores_num = cores_num
    return p


def _plugin_types(setup: DebugSetup) -> list:
    return [type(plugin) for plugin in setup.plugins]


class TestDebugSetupCreate:
    def test_no_products(self) -> None:
        setup = get_debug_setup([])
        assert setup.plugins == []

    def test_nothing_enabled(self) -> None:
        setup = get_debug_setup([_make_product()])
        assert setup.plugins == []

    def test_coredump_without_handlers(self) -> None:
        p = _make_product(debug={"coredump": {"enable": True}})
        setup = get_debug_setup([p])
        assert _plugin_types(setup) == [CoredumpPlugin]
        mgr = setup.plugins[0]._managers["prod"]
        assert mgr._handlers == []
        assert setup.plugins[0]._products == [p]

    def test_gdb_handler_registered(self) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "gdb": {"enable": True, "target": "localhost:1234"},
            },
            elf="/fw/nuttx",
        )
        with (
            patch("ntfc.debug.getdebug.GdbController") as ctrl_cls,
            patch("ntfc.debug.getdebug.GdbHandler") as handler_cls,
        ):
            setup = get_debug_setup([p])
        args, ctrl_kwargs = ctrl_cls.call_args
        assert args == (Path("/fw/nuttx"), p.conf.debug.gdb)
        assert callable(ctrl_kwargs["pid_provider"])
        _, handler_kwargs = handler_cls.call_args
        assert handler_cls.call_args.args == (ctrl_cls.return_value,)
        assert handler_kwargs["force_panic"] is None
        assert callable(handler_kwargs["crash_check"])
        assert handler_kwargs["auto_dump"] is False
        mgr = setup.plugins[0]._managers["prod"]
        assert mgr._handlers == [handler_cls.return_value]
        assert setup._controllers_by_product == {
            "prod": [ctrl_cls.return_value]
        }

    def test_gdb_handler_gets_force_panic_callable(self) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "gdb": {
                    "enable": True,
                    "target": "localhost:1234",
                    "force_panic": True,
                },
            },
            elf="/fw/nuttx",
        )
        with (
            patch("ntfc.debug.getdebug.GdbController"),
            patch("ntfc.debug.getdebug.GdbHandler") as handler_cls,
        ):
            get_debug_setup([p])
        _, kwargs = handler_cls.call_args
        assert kwargs["force_panic"] is p.force_panic

    def test_gdb_enabled_without_elf_skipped(self) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "gdb": {"enable": True, "target": "localhost:1234"},
            },
            elf="",
        )
        setup = get_debug_setup([p])
        mgr = setup.plugins[0]._managers["prod"]
        assert mgr._handlers == []
        assert setup._controllers_by_product == {"prod": []}

    def test_gdb_enabled_without_target_or_attach_skipped(self) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "gdb": {"enable": True},
            },
            elf="/fw/nuttx",
        )
        setup = get_debug_setup([p])
        mgr = setup.plugins[0]._managers["prod"]
        assert mgr._handlers == []
        assert setup._controllers_by_product == {"prod": []}

    def test_gdb_attach_mode_registers_with_pid_provider(self) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "gdb": {"enable": True, "attach": True},
            },
            elf="/fw/nuttx",
        )
        p.core.return_value.device.pid = 4242
        with (
            patch("ntfc.debug.getdebug.GdbController") as ctrl_cls,
            patch("ntfc.debug.getdebug.GdbHandler"),
        ):
            get_debug_setup([p])
        _, kwargs = ctrl_cls.call_args
        assert kwargs["pid_provider"]() == 4242

    def test_gdb_handler_gets_crash_check_and_auto_dump(self) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "gdb": {
                    "enable": True,
                    "target": "localhost:1234",
                    "plugin": True,
                    "auto_breakpoints": True,
                },
            },
            elf="/fw/nuttx",
        )
        p.crash = True
        with (
            patch("ntfc.debug.getdebug.GdbController"),
            patch("ntfc.debug.getdebug.GdbHandler") as handler_cls,
        ):
            get_debug_setup([p])
        _, kwargs = handler_cls.call_args
        assert kwargs["auto_dump"] is True
        assert kwargs["crash_check"]() is True

    def test_local_file_handler_registered(self, tmp_path: Path) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "local_file": {"core_dir": str(tmp_path)},
            }
        )
        setup = get_debug_setup([p])
        mgr = setup.plugins[0]._managers["prod"]
        assert [h.name for h in mgr._handlers] == ["local_file"]

    def test_syslog_handler_registered(self) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "syslog": {"enable": True},
            }
        )
        setup = get_debug_setup([p])
        mgr = setup.plugins[0]._managers["prod"]
        assert [h.name for h in mgr._handlers] == ["syslog"]

    def test_fastboot_handler_registered(self) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "fastboot": {
                    "dev_sn": "SN1",
                    "mem_addr": "0x1000",
                    "mem_size": "0x2000",
                },
            }
        )
        with (
            patch("ntfc.debug.getdebug.FastbootController") as ctrl_cls,
            patch("ntfc.debug.getdebug.FastbootHandler") as handler_cls,
        ):
            setup = get_debug_setup([p])
        ctrl_cls.assert_called_once_with("SN1")
        handler_cls.assert_called_once_with(
            ctrl_cls.return_value, "0x1000", "0x2000"
        )
        mgr = setup.plugins[0]._managers["prod"]
        assert mgr._handlers == [handler_cls.return_value]

    def test_ymodem_handler_registered(self) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "ymodem": {
                    "serial_port": "/dev/ttyUSB0",
                    "baud_rate": 115200,
                    "sbrb_path": "/tools/sbrb.py",
                },
            }
        )
        with (
            patch("ntfc.debug.getdebug.YmodemController") as ctrl_cls,
            patch("ntfc.debug.getdebug.YmodemHandler") as handler_cls,
        ):
            setup = get_debug_setup([p])
        ctrl_cls.assert_called_once_with(
            "/dev/ttyUSB0", Path("/tools/sbrb.py"), 115200
        )
        handler_cls.assert_called_once_with(
            ctrl_cls.return_value, p.core.return_value.device
        )
        mgr = setup.plugins[0]._managers["prod"]
        assert mgr._handlers == [handler_cls.return_value]

    def test_ymodem_requires_serial_and_sbrb(self) -> None:
        p = _make_product(
            debug={
                "coredump": {"enable": True},
                "ymodem": {"serial_port": "/dev/ttyUSB0"},
            }
        )
        setup = get_debug_setup([p])
        mgr = setup.plugins[0]._managers["prod"]
        assert mgr._handlers == []

    def test_multicore_product_warns_but_registers(
        self, caplog: "pytest.LogCaptureFixture"
    ) -> None:
        p = _make_product(debug={"coredump": {"enable": True}}, cores_num=2)
        with caplog.at_level("WARNING"):
            setup = get_debug_setup([p])
        assert "only supports core 0" in caplog.text
        assert _plugin_types(setup) == [CoredumpPlugin]

    def test_multiple_products(self) -> None:
        p1 = _make_product(name="p1", debug={"coredump": {"enable": True}})
        p2 = _make_product(name="p2", debug={"coredump": {"enable": True}})
        setup = get_debug_setup([p1, p2])
        assert _plugin_types(setup) == [CoredumpPlugin]
        assert list(setup.plugins[0]._managers) == ["p1", "p2"]


class TestDebugSetup:
    def test_plugins_returns_copy(self) -> None:
        plugin = MagicMock()
        setup = DebugSetup([plugin], {})
        plugins = setup.plugins
        plugins.append(MagicMock())
        assert setup.plugins == [plugin]

    def test_start_and_stop(self) -> None:
        ctrl = MagicMock()
        ctrl.start.return_value = True
        setup = DebugSetup([], {"prod": [ctrl]})
        setup.start("/results")
        ctrl.start.assert_called_once()
        ctrl.setup.assert_called_once_with("/results/prod")
        setup.stop()
        ctrl.stop.assert_called_once()
        # stop() clears the started list
        setup.stop()
        ctrl.stop.assert_called_once()

    def test_start_failure_skips_setup(self) -> None:
        good = MagicMock()
        good.start.return_value = True
        bad = MagicMock()
        bad.start.return_value = False
        setup = DebugSetup([], {"prod": [bad, good]})
        setup.start("/results")
        bad.setup.assert_not_called()
        good.setup.assert_called_once_with("/results/prod")
        setup.stop()
        bad.stop.assert_not_called()
        good.stop.assert_called_once()

    def test_start_noop_without_result_dir(self) -> None:
        ctrl = MagicMock()
        setup = DebugSetup([], {"prod": [ctrl]})
        setup.start("")
        ctrl.start.assert_not_called()

    def test_restart_controllers_reattaches(self) -> None:
        ctrl = MagicMock()
        ctrl.start.return_value = True
        setup = DebugSetup([], {"prod": [ctrl]})
        setup.start("/results")
        ctrl.start.reset_mock()
        ctrl.setup.reset_mock()

        setup.restart_controllers("prod")

        ctrl.stop.assert_called_once()
        ctrl.start.assert_called_once()
        ctrl.setup.assert_called_once_with("/results/prod")

    def test_restart_controllers_starts_previously_failed(self) -> None:
        ctrl = MagicMock()
        ctrl.start.return_value = False
        setup = DebugSetup([], {"prod": [ctrl]})
        setup.start("/results")
        ctrl.start.assert_called_once()

        ctrl.start.return_value = True
        setup.restart_controllers("prod")

        # never started, so no stop() before the retry
        ctrl.stop.assert_not_called()
        assert ctrl.start.call_count == 2

    def test_restart_controllers_unknown_product_is_noop(self) -> None:
        setup = DebugSetup([], {})
        setup.start("/results")
        setup.restart_controllers("missing")  # must not raise

    def test_restart_controllers_noop_before_start(self) -> None:
        ctrl = MagicMock()
        setup = DebugSetup([], {"prod": [ctrl]})
        setup.restart_controllers("prod")
        ctrl.start.assert_not_called()

    def test_restart_all_controllers_restarts_every_product(self) -> None:
        ctrl_a = MagicMock()
        ctrl_a.start.return_value = True
        ctrl_b = MagicMock()
        ctrl_b.start.return_value = True
        setup = DebugSetup([], {"a": [ctrl_a], "b": [ctrl_b]})
        setup.start("/results")
        ctrl_a.start.reset_mock()
        ctrl_b.start.reset_mock()

        setup.restart_all_controllers()

        ctrl_a.stop.assert_called_once()
        ctrl_a.start.assert_called_once()
        ctrl_b.stop.assert_called_once()
        ctrl_b.start.assert_called_once()
