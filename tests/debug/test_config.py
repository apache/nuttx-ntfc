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

import pytest

from ntfc.debug.config import (
    CoredumpConfig,
    DebugConfig,
    FastbootConfig,
    GdbConfig,
    LocalFileConfig,
    SyslogConfig,
    YmodemConfig,
)


class TestCoredumpConfig:
    def test_defaults(self):
        cfg = CoredumpConfig({})
        assert cfg.enable is False
        assert cfg.collection_type == "auto"
        assert cfg.limit == 5

    def test_full_config(self):
        cfg = CoredumpConfig({"enable": True, "type": "gdb", "limit": 10})
        assert cfg.enable is True
        assert cfg.collection_type == "gdb"
        assert cfg.limit == 10

    def test_all_valid_types(self):
        for t in ("auto", "gdb", "fastboot", "ymodem"):
            cfg = CoredumpConfig({"type": t})
            assert cfg.collection_type == t

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Invalid coredump type"):
            CoredumpConfig({"type": "invalid"})

    def test_enable_false(self):
        cfg = CoredumpConfig({"enable": False})
        assert cfg.enable is False

    def test_limit_zero(self):
        cfg = CoredumpConfig({"limit": 0})
        assert cfg.limit == 0


class TestGdbConfig:
    def test_defaults(self):
        cfg = GdbConfig({})
        assert cfg.enable is False
        assert cfg.force_panic is False
        assert cfg.target == ""

    def test_full_config(self):
        cfg = GdbConfig({"enable": True, "force_panic": True})
        assert cfg.enable is True
        assert cfg.force_panic is True

    def test_enable_only(self):
        cfg = GdbConfig({"enable": True})
        assert cfg.enable is True
        assert cfg.force_panic is False

    def test_force_panic_only(self):
        cfg = GdbConfig({"force_panic": True})
        assert cfg.enable is False
        assert cfg.force_panic is True

    def test_target_tcp(self):
        cfg = GdbConfig({"target": "localhost:1234"})
        assert cfg.target == "localhost:1234"

    def test_target_unix_socket(self):
        cfg = GdbConfig({"target": "/tmp/gdb.socket"})
        assert cfg.target == "/tmp/gdb.socket"

    def test_target_default_empty(self):
        cfg = GdbConfig({})
        assert cfg.target == ""

    def test_gdb_path_default(self):
        cfg = GdbConfig({})
        assert cfg.gdb_path == "gdb"

    def test_gdb_path_custom(self):
        cfg = GdbConfig({"gdb_path": "gdb-multiarch"})
        assert cfg.gdb_path == "gdb-multiarch"

    def test_plugin_default(self):
        cfg = GdbConfig({})
        assert cfg.plugin is False

    def test_plugin_enabled(self):
        cfg = GdbConfig({"plugin": True})
        assert cfg.plugin is True

    def test_setup_cmds_default_empty(self):
        cfg = GdbConfig({})
        assert cfg.setup_cmds == []

    def test_setup_cmds_parsed(self):
        cmds = ["break main", "continue"]
        cfg = GdbConfig({"setup_cmds": cmds})
        assert cfg.setup_cmds == cmds

    def test_setup_cmds_copy_returned(self):
        cfg = GdbConfig({"setup_cmds": ["break main"]})
        cfg.setup_cmds.append("mutated")
        assert cfg.setup_cmds == ["break main"]


class TestFastbootConfig:
    def test_defaults(self):
        cfg = FastbootConfig({})
        assert cfg.dev_sn == ""
        assert cfg.mem_addr == "0x40000000"
        assert cfg.mem_size == "0x08000000"

    def test_custom_dev_sn(self):
        cfg = FastbootConfig({"dev_sn": "ABC123"})
        assert cfg.dev_sn == "ABC123"

    def test_custom_mem_region(self):
        cfg = FastbootConfig(
            {"mem_addr": "0x20000000", "mem_size": "0x04000000"}
        )
        assert cfg.mem_addr == "0x20000000"
        assert cfg.mem_size == "0x04000000"

    def test_full_config(self):
        cfg = FastbootConfig(
            {
                "dev_sn": "XYZ999",
                "mem_addr": "0x10000000",
                "mem_size": "0x01000000",
            }
        )
        assert cfg.dev_sn == "XYZ999"
        assert cfg.mem_addr == "0x10000000"
        assert cfg.mem_size == "0x01000000"


class TestYmodemConfig:
    def test_defaults(self):
        cfg = YmodemConfig({})
        assert cfg.serial_port == ""
        assert cfg.baud_rate == 921600
        assert cfg.sbrb_path == ""

    def test_custom_serial_port(self):
        cfg = YmodemConfig({"serial_port": "/dev/ttyUSB0"})
        assert cfg.serial_port == "/dev/ttyUSB0"

    def test_custom_baud_rate(self):
        cfg = YmodemConfig({"baud_rate": 115200})
        assert cfg.baud_rate == 115200

    def test_custom_sbrb_path(self):
        cfg = YmodemConfig({"sbrb_path": "/opt/tools/sbrb.py"})
        assert cfg.sbrb_path == "/opt/tools/sbrb.py"

    def test_full_config(self):
        cfg = YmodemConfig(
            {
                "serial_port": "/dev/ttyUSB1",
                "baud_rate": 460800,
                "sbrb_path": "/tools/sbrb.py",
            }
        )
        assert cfg.serial_port == "/dev/ttyUSB1"
        assert cfg.baud_rate == 460800
        assert cfg.sbrb_path == "/tools/sbrb.py"


class TestDebugConfig:
    def test_defaults_empty(self):
        cfg = DebugConfig({})
        assert cfg.coredump.enable is False
        assert cfg.coredump.collection_type == "auto"
        assert cfg.coredump.limit == 5
        assert cfg.gdb.enable is False
        assert cfg.gdb.force_panic is False
        assert cfg.gdb.target == ""
        assert cfg.fastboot.dev_sn == ""
        assert cfg.fastboot.mem_addr == "0x40000000"
        assert cfg.ymodem.serial_port == ""
        assert cfg.ymodem.baud_rate == 921600
        assert cfg.ymodem.sbrb_path == ""

    def test_full_config(self):
        cfg = DebugConfig(
            {
                "coredump": {
                    "enable": True,
                    "type": "fastboot",
                    "limit": 3,
                },
                "gdb": {
                    "enable": True,
                    "force_panic": True,
                },
                "fastboot": {
                    "dev_sn": "ABC123",
                },
                "ymodem": {
                    "serial_port": "/dev/ttyUSB0",
                    "sbrb_path": "/tools/sbrb.py",
                },
            }
        )
        assert cfg.coredump.enable is True
        assert cfg.coredump.collection_type == "fastboot"
        assert cfg.coredump.limit == 3
        assert cfg.gdb.enable is True
        assert cfg.gdb.force_panic is True
        assert cfg.fastboot.dev_sn == "ABC123"
        assert cfg.ymodem.serial_port == "/dev/ttyUSB0"
        assert cfg.ymodem.sbrb_path == "/tools/sbrb.py"

    def test_coredump_only(self):
        cfg = DebugConfig({"coredump": {"enable": True}})
        assert cfg.coredump.enable is True
        assert cfg.gdb.enable is False

    def test_gdb_only(self):
        cfg = DebugConfig({"gdb": {"enable": True}})
        assert cfg.coredump.enable is False
        assert cfg.gdb.enable is True

    def test_invalid_coredump_type_propagates(self):
        with pytest.raises(ValueError, match="Invalid coredump type"):
            DebugConfig({"coredump": {"type": "unknown"}})


class TestGdbConfigParity:
    def test_new_defaults(self):
        cfg = GdbConfig({})
        assert cfg.gcore_cmd == "gcore"
        assert cfg.nx_plugin == ""
        assert cfg.osabi == ""
        assert cfg.auto_breakpoints is False
        assert cfg.mmleak is False
        assert cfg.attach is False
        assert cfg.use_sudo is False

    def test_new_values(self):
        cfg = GdbConfig(
            {
                "plugin": True,
                "gcore_cmd": "gcore -t",
                "nx_plugin": "/nx/gdbinit.py",
                "osabi": "none",
                "auto_breakpoints": True,
                "mmleak": True,
                "attach": True,
                "use_sudo": True,
            }
        )
        assert cfg.gcore_cmd == "gcore -t"
        assert cfg.nx_plugin == "/nx/gdbinit.py"
        assert cfg.osabi == "none"
        assert cfg.auto_breakpoints is True
        assert cfg.mmleak is True
        assert cfg.attach is True
        assert cfg.use_sudo is True

    def test_auto_breakpoints_requires_plugin(self):
        with pytest.raises(ValueError, match="auto_breakpoints"):
            GdbConfig({"auto_breakpoints": True})

    def test_mmleak_requires_auto_breakpoints(self):
        with pytest.raises(ValueError, match="mmleak"):
            GdbConfig({"plugin": True, "mmleak": True})

    def test_attach_and_target_mutually_exclusive(self):
        with pytest.raises(ValueError, match="attach"):
            GdbConfig({"attach": True, "target": "localhost:1234"})


class TestLocalFileConfig:
    def test_defaults(self):
        cfg = LocalFileConfig({})
        assert cfg.core_dir == ""
        assert cfg.pattern == "*.core"

    def test_values(self):
        cfg = LocalFileConfig({"core_dir": "/tmp/x", "pattern": "core*"})
        assert cfg.core_dir == "/tmp/x"
        assert cfg.pattern == "core*"


class TestSyslogConfig:
    def test_defaults(self):
        assert SyslogConfig({}).enable is False

    def test_enabled(self):
        assert SyslogConfig({"enable": True}).enable is True


class TestDebugConfigParity:
    def test_new_sections(self):
        cfg = DebugConfig(
            {
                "local_file": {"core_dir": "/cores"},
                "syslog": {"enable": True},
            }
        )
        assert cfg.local_file.core_dir == "/cores"
        assert cfg.syslog.enable is True

    def test_new_coredump_types_valid(self):
        for t in ("local_file", "syslog"):
            assert CoredumpConfig({"type": t}).collection_type == t
