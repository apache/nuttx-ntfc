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

import shutil

import pytest

from ntfc.coreconfig import CoreConfig


def test_product_core_config():
    conf = {
        "name": "dummy",
        "device": "sim",
        "elf_path": "./tests/resources/nuttx/sim/nuttx",
        "conf_path": "./tests/resources/nuttx/sim/kv_config",
        "uptime": 1,
    }

    p = CoreConfig(conf)

    assert p.elf_path == "./tests/resources/nuttx/sim/nuttx"
    assert p.kv_check("aaa") is False
    assert p.kv_check("CONFIG_SYSTEM_NSH") is True

    # check hex conversion
    assert p.kv_check("CONFIG_SYSLOG_DEFAULT_MASK") == 0xFF

    assert p.cmd_check("aaa") is False
    assert p.cmd_check("hello_main") is True

    conf = {
        "name": "product",
    }

    p = CoreConfig(conf)

    with pytest.raises(AttributeError):
        p.cmd_check("aaa")

    # kv_check returns False when no config data
    # instead of raising an exception
    assert p.kv_check("aaa") is False


def test_load_core_config_malformed_line(tmp_path):
    cfg_file = tmp_path / "kv_config"
    cfg_file.write_text(
        "# comment\n" "\n" "MALFORMED_NO_EQUALS\n" "CONFIG_SYSTEM_NSH=y\n"
    )
    conf = {"name": "dummy", "conf_path": str(cfg_file)}
    p = CoreConfig(conf)
    # malformed line is skipped; valid line is loaded
    assert p.kv_check("CONFIG_SYSTEM_NSH") is True
    assert p.kv_check("MALFORMED_NO_EQUALS") is False


def test_load_core_config_value_types(tmp_path):
    cfg_file = tmp_path / "kv_config_types"
    cfg_file.write_text(
        "CONFIG_DECIMAL=123\n"
        "CONFIG_HEX=0x10\n"
        "CONFIG_BOOL_Y=y\n"
        "CONFIG_BOOL_N=n\n"
        'CONFIG_QUOTED="hello"\n'
        "CONFIG_UNQUOTED=plain_text\n"
        'CONFIG_QUOTED_HEX="{0x40000000,0x100}"\n'
        "CONFIG_BAD_HEX=0xZZ\n"
    )
    conf = {"name": "dummy", "conf_path": str(cfg_file)}
    p = CoreConfig(conf)

    assert p.kv_check("CONFIG_DECIMAL") == 123
    assert p.kv_check("CONFIG_HEX") == 0x10
    assert p.kv_check("CONFIG_BOOL_Y") is True
    assert p.kv_check("CONFIG_BOOL_N") is False
    assert p.kv_check("CONFIG_QUOTED") == "hello"
    assert p.kv_check("CONFIG_UNQUOTED") == "plain_text"
    # quoted values containing hex digits must stay strings
    assert p.kv_check("CONFIG_QUOTED_HEX") == "{0x40000000,0x100}"
    # unparsable hex falls back to the raw string
    assert p.kv_check("CONFIG_BAD_HEX") == "0xZZ"


def test_core_config_flash_only_property():
    conf = {"name": "test", "flash_only": True}
    assert CoreConfig(conf).flash_only is True
    assert CoreConfig({"name": "test"}).flash_only is False


def test_core_config_is_kernel_build(tmp_path):
    cfg_file = tmp_path / "kv_config"
    cfg_file.write_text("CONFIG_BUILD_KERNEL=y\n")
    assert (
        CoreConfig({"name": "t", "conf_path": str(cfg_file)}).is_kernel_build
        is True
    )

    cfg_file.write_text("CONFIG_BUILD_FLAT=y\n")
    assert (
        CoreConfig({"name": "t", "conf_path": str(cfg_file)}).is_kernel_build
        is False
    )

    # no .config at all
    assert CoreConfig({"name": "t"}).is_kernel_build is False


def test_core_config_exec_cwd():
    assert (
        CoreConfig({"name": "t", "exec_cwd": "/some/dir"}).exec_cwd
        == "/some/dir"
    )
    assert CoreConfig({"name": "t"}).exec_cwd is None


def test_core_config_boot_timeout():
    assert CoreConfig({"name": "t", "boot_timeout": 15}).boot_timeout == 15
    assert CoreConfig({"name": "t"}).boot_timeout == 5


def test_core_config_app_bindir(tmp_path):
    kernel_cfg = tmp_path / "kv_config"
    kernel_cfg.write_text("CONFIG_BUILD_KERNEL=y\n")

    # explicit YAML value always wins
    conf = {"name": "t", "app_bindir": "/custom/bin"}
    assert CoreConfig(conf).app_bindir == "/custom/bin"

    # kernel build: derived from elf_path sibling bin/
    conf = {
        "name": "t",
        "conf_path": str(kernel_cfg),
        "elf_path": "./tests/resources/nuttx/sim/nuttx",
    }
    assert CoreConfig(conf).app_bindir == "./tests/resources/nuttx/sim/bin"

    # kernel build without elf_path: nothing to derive from
    assert (
        CoreConfig({"name": "t", "conf_path": str(kernel_cfg)}).app_bindir
        is None
    )

    # flat build: never derived
    conf = {
        "name": "t",
        "conf_path": "./tests/resources/nuttx/sim/kv_config",
        "elf_path": "./tests/resources/nuttx/sim/nuttx",
    }
    assert CoreConfig(conf).app_bindir is None

    # a derived directory that does not exist is not a command source
    conf = {
        "name": "t",
        "conf_path": str(kernel_cfg),
        "elf_path": "./tests/resources/nuttx/sim/nuttx",
    }
    core_conf = CoreConfig(conf)
    assert core_conf.app_bindir == "./tests/resources/nuttx/sim/bin"
    assert core_conf.has_app_bindir is False


def test_core_config_cmd_check_kernel_mode(tmp_path):
    kernel_cfg = tmp_path / "kv_config"
    kernel_cfg.write_text("CONFIG_BUILD_KERNEL=y\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "hello").write_bytes(b"\x7fELF" + b"\x00" * 12)

    conf = {
        "name": "t",
        "conf_path": str(kernel_cfg),
        "app_bindir": str(bindir),
    }

    p = CoreConfig(conf)
    assert p.has_app_bindir is True
    # command resolution by application file name, no ELF configured
    assert p.cmd_check("hello") is True
    assert p.cmd_check("hello_main") is True
    assert p.cmd_check("cmd_df") is False

    # symbol fallback over unstripped binaries in bin_debug
    debug = tmp_path / "bin_debug"
    debug.mkdir()
    shutil.copy("./tests/resources/nuttx/sim/nuttx", debug / "sh")

    p = CoreConfig(conf)
    assert p.cmd_check("cmd_df") is True
    assert p.cmd_check("missing|cmd_df") is True
    assert p.cmd_check("cmd_d.*") is True
    assert p.cmd_check("no_such_symbol_xyz") is False


def test_core_config_read_poll_interval() -> None:
    assert CoreConfig({"name": "test"}).read_poll_interval == 0.1
    assert (
        CoreConfig(
            {"name": "test", "read_poll_interval": 0.001}
        ).read_poll_interval
        == 0.001
    )
    with pytest.raises(ValueError, match="must be positive"):
        _ = CoreConfig(
            {"name": "test", "read_poll_interval": 0}
        ).read_poll_interval


def test_core_config_os_defaults_to_nuttx() -> None:
    assert CoreConfig({"name": "test"}).os == "nuttx"
    assert CoreConfig({"name": "test", "os": "Linux"}).os == "linux"


def test_linux_kernel_image_does_not_require_elf_symbols(tmp_path) -> None:
    image = tmp_path / "bzImage"
    image.write_bytes(b"not-an-elf")

    core = CoreConfig({"name": "linux", "os": "linux", "elf_path": str(image)})

    assert core.elf_path == str(image)
    with pytest.raises(AttributeError):
        core.cmd_check("rtbench")


def test_core_config_prompt():
    # Test with explicit prompt in YAML config
    conf = {
        "name": "test",
        "device": "sim",
        "prompt": "custom_prompt>",
    }

    p = CoreConfig(conf)
    assert p.prompt == "custom_prompt>"

    # Test without explicit prompt, loads from config file
    conf = {
        "name": "test",
        "device": "sim",
        "conf_path": "./tests/resources/nuttx/sim/kv_config",
    }

    p = CoreConfig(conf)
    # Should load from kv_config file or return None
    assert p.prompt == "nsh> "


def test_core_config_cmd_check_label_prefix(mocker):
    result = mocker.Mock()
    result.stdout = "00000100 T _nx_start\n00000200 T _ostest_main\n"
    mocker.patch("ntfc.lib.elf.elf_parser.subprocess.run", return_value=result)

    conf = {
        "name": "dummy",
        "device": "qemu",
        "elf_path": "./tests/resources/nuttx/sim/nuttx",
        "conf_path": "./tests/resources/nuttx/sim/kv_config",
    }

    p = CoreConfig(conf)

    assert p.cmd_check("ostest_main") is True
    assert p.cmd_check("missing|ostest_main") is True
    assert p.cmd_check("ostest.*") is True
    assert p.cmd_check("_ostest_main") is False
