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

import copy
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ntfc.builder import BuilderConfigError, NuttXBuilder

conf_dir = {
    "config": {"cwd": "aaa", "build_dir": "bbb"},
    "product": {
        "name": "xxx",
        "cores": {
            "core0": {
                "name": "dummy",
                "device": "sim",
            }
        },
    },
}


def builder_run_command_dummy(cmd, env):
    pass


def builder_make_dir_dummy(path):
    pass


def test_builder_init():

    with pytest.raises(TypeError):
        _ = NuttXBuilder(None)

    b = NuttXBuilder(conf_dir)

    assert b.need_build() is False

    conf_dir["product"]["cores"]["core0"]["defconfig"] = "dummy/path"
    assert b.need_build() is True

    b._run_command = builder_run_command_dummy
    b._make_dir = builder_make_dir_dummy

    b.build_all()

    new_confg = b.new_conf()
    assert new_confg is not None

    assert (
        new_confg["product"]["cores"]["core0"]["elf_path"]
        == "bbb/product-xxx-dummy/nuttx"
    )
    assert (
        new_confg["product"]["cores"]["core0"]["conf_path"]
        == "bbb/product-xxx-dummy/.config"
    )


def test_builder_passes_build_env() -> None:
    config = copy.deepcopy(conf_dir)
    config["config"]["build_env"] = {"CC": "gcc-13", "CXX": "g++-13"}
    config["product"]["cores"]["core0"]["defconfig"] = "dummy/path"
    config["product"]["cores"]["core0"]["build_env"] = {"CXX": "g++-14"}

    calls = []

    def run_command_capture(cmd, env):
        calls.append((cmd, env))

    b = NuttXBuilder(config)
    b._run_command = run_command_capture
    b._make_dir = builder_make_dir_dummy

    b.build_all()

    assert len(calls) == 2
    assert calls[0][0][0] == "cmake"
    assert calls[1][0][:2] == ["cmake", "--build"]
    assert calls[0][1]["CC"] == "gcc-13"
    assert calls[0][1]["CXX"] == "g++-14"
    assert calls[1][1]["CC"] == "gcc-13"
    assert calls[1][1]["CXX"] == "g++-14"


def test_builder_regenerates_config_after_kconfig_overrides() -> None:
    config = copy.deepcopy(conf_dir)
    config["product"]["cores"]["core0"]["defconfig"] = "dummy/path"
    config["product"]["cores"]["core0"]["kv"] = {
        "CONFIG_ARCH_X86_64_IDLE_NOP": True
    }
    calls = []

    builder = NuttXBuilder(config)
    builder._run_command = lambda command, env: calls.append(command)
    builder._make_dir = builder_make_dir_dummy
    builder._apply_kconfig_overrides = lambda *_args: None
    builder.build_all()

    assert calls[1] == [
        "cmake",
        "--build",
        "bbb/product-xxx-dummy",
        "--target",
        "olddefconfig",
    ]
    assert calls[2] == ["cmake", "--build", "bbb/product-xxx-dummy"]


def test_builder_run_build_target_passes_env() -> None:
    builder = NuttXBuilder(copy.deepcopy(conf_dir))
    calls = []
    builder._run_command = lambda command, env: calls.append((command, env))

    builder._run_build_target("build-dir", "olddefconfig", {"CC": "gcc-13"})

    assert calls[0][0] == [
        "cmake",
        "--build",
        "build-dir",
        "--target",
        "olddefconfig",
    ]
    assert calls[0][1]["CC"] == "gcc-13"


def test_builder_ignores_invalid_build_env_types() -> None:
    config = copy.deepcopy(conf_dir)
    config["config"]["build_env"] = "CC=gcc-14 CXX=g++-14"
    config["product"]["cores"]["core0"]["build_env"] = ["CC", "gcc-14"]

    b = NuttXBuilder(config)

    assert b._get_build_env(config["product"]["cores"]["core0"]) == {}


def test_builder_supports_dcmake_dict_syntax() -> None:
    config = copy.deepcopy(conf_dir)
    config["product"]["cores"]["core0"]["defconfig"] = "dummy/path"
    config["product"]["cores"]["core0"]["dcmake"] = {
        "CCACHE": "ON",
        "SOME_NUMBER": 1,
    }

    calls = []

    def run_command_capture(cmd, env):
        calls.append((cmd, env))

    b = NuttXBuilder(config)
    b._run_command = run_command_capture
    b._make_dir = builder_make_dir_dummy

    b.build_all()

    cmake_cmd = calls[0][0]
    assert "-DBOARD_CONFIG=dummy/path" in cmake_cmd
    assert "-DCCACHE=ON" in cmake_cmd
    assert "-DSOME_NUMBER=1" in cmake_cmd


def test_builder_get_cmake_defines_ignores_invalid_type() -> None:
    b = NuttXBuilder(copy.deepcopy(conf_dir))
    assert b._get_cmake_defines({"dcmake": "A=1"}, "defcfg") == {
        "BOARD_CONFIG": "defcfg"
    }


def test_builder_accepts_explicit_nuttx_and_apps_directories(tmp_path) -> None:
    config = copy.deepcopy(conf_dir)
    build_dir = tmp_path / "build"
    nuttx_dir = tmp_path / "source" / "nuttx-custom"
    apps_dir = tmp_path / "source" / "apps-custom"
    nuttx_dir.mkdir(parents=True)
    apps_dir.mkdir(parents=True)
    config["config"].update(
        {
            "build_dir": str(build_dir),
            "nuttx_dir": str(nuttx_dir),
            "apps_dir": str(apps_dir),
        }
    )
    config["product"]["cores"]["core0"]["defconfig"] = "board:test"
    calls = []

    builder = NuttXBuilder(config)
    builder._run_command = lambda command, env: calls.append(command)
    builder._make_dir = lambda _path: None
    builder.build_all()

    configure = calls[0]
    assert f"-S{nuttx_dir}" in configure
    assert f"-DNUTTX_APPS_DIR={apps_dir}" in configure


def test_builder_kconfig_helpers() -> None:
    b = NuttXBuilder(copy.deepcopy(conf_dir))
    core_cfg = {"kv": {"CONFIG_CORE": "m"}}

    assert b._get_kconfig_overrides() == {}
    b._cfg_values["config"]["kv"] = "invalid"
    assert b._get_kconfig_overrides() == {}
    b._cfg_values["config"]["kv"] = {"CONFIG_X": "y"}
    assert b._get_kconfig_overrides() == {"CONFIG_X": "y"}
    assert b._get_kconfig_overrides(core_cfg) == {
        "CONFIG_X": "y",
        "CONFIG_CORE": "m",
    }
    assert b._get_kconfig_overrides({"kv": "invalid"}) == {"CONFIG_X": "y"}
    b._cfg_values["config"]["kv"] = {"CONFIG_X": "y", "CONFIG_A": "1"}
    core_cfg = {"kv": {"CONFIG_X": "n", "CONFIG_B": "2"}}
    assert b._get_kconfig_overrides(core_cfg) == {
        "CONFIG_X": "n",
        "CONFIG_A": "1",
        "CONFIG_B": "2",
    }
    assert b._valid_kconfig_overrides({"CONFIG_X": "y", 1: "BAD"}) == {
        "CONFIG_X": "y"
    }
    assert b._valid_kconfig_overrides([["CONFIG_X", "y"], ["BAD"], 1]) == {
        "CONFIG_X": "y"
    }

    assert b._format_kconfig_line("CONFIG_A", False) == (
        "# CONFIG_A is not set\n"
    )
    assert b._format_kconfig_line("CONFIG_A", True) == "CONFIG_A=y\n"
    assert b._format_kconfig_line("CONFIG_A", 10) == "CONFIG_A=10\n"
    assert b._format_kconfig_line("CONFIG_A", "n") == (
        "# CONFIG_A is not set\n"
    )
    assert b._format_kconfig_line("CONFIG_A", "m") == "CONFIG_A=m\n"
    assert b._format_kconfig_line("CONFIG_A", '"abc"') == 'CONFIG_A="abc"\n'
    assert b._format_kconfig_line("CONFIG_A", "0x20") == "CONFIG_A=0x20\n"
    assert b._format_kconfig_line("CONFIG_A", "123") == "CONFIG_A=123\n"
    assert b._format_kconfig_line("CONFIG_A", "abc") == 'CONFIG_A="abc"\n'
    assert b._format_kconfig_line("CONFIG_A", 1.5) == 'CONFIG_A="1.5"\n'


def test_builder_find_kconfig_tweak() -> None:
    b = NuttXBuilder(copy.deepcopy(conf_dir))

    with patch("ntfc.builder.shutil.which", return_value="/usr/bin/kt"):
        assert b._find_kconfig_tweak("/tmp/x") == "/usr/bin/kt"

    with patch("ntfc.builder.shutil.which", return_value=None):
        assert b._find_kconfig_tweak("/definitely/missing") is None


def test_builder_apply_kconfig_overrides_kconfig_tweak() -> None:
    b = NuttXBuilder(copy.deepcopy(conf_dir))
    calls = []

    def fake_run(cmd):
        calls.append(cmd)

    b._find_kconfig_tweak = lambda _cwd: "/usr/bin/kconfig-tweak"
    b._run_kconfig_tweak_cmd = fake_run

    assert (
        b._apply_kconfig_overrides_kconfig_tweak(
            "/tmp/.config",
            {
                "CONFIG_FALSE": False,
                "CONFIG_TRUE": True,
                "CONFIG_MOD": "m",
                "CONFIG_INT": 10,
                "CONFIG_HEX": "0x20",
                "CONFIG_STR_QUOTED": '"abc"',
                "CONFIG_STR": "abc",
                "CONFIG_OTHER": 1.5,
            },
            "/tmp",
        )
        is True
    )

    assert calls[0] == [
        "/usr/bin/kconfig-tweak",
        "--file",
        "/tmp/.config",
        "--disable",
        "CONFIG_FALSE",
    ]
    assert any("--enable" in cmd and "CONFIG_TRUE" in cmd for cmd in calls)
    assert any("--module" in cmd and "CONFIG_MOD" in cmd for cmd in calls)
    assert any("--set-val" in cmd and "CONFIG_INT" in cmd for cmd in calls)
    assert any("--set-val" in cmd and "CONFIG_HEX" in cmd for cmd in calls)
    assert any(
        cmd[-3:] == ["--set-str", "CONFIG_STR_QUOTED", "abc"] for cmd in calls
    )
    assert any("--set-str" in cmd and "CONFIG_STR" in cmd for cmd in calls)
    assert any("--set-str" in cmd and "CONFIG_OTHER" in cmd for cmd in calls)


def test_builder_apply_kconfig_overrides_kconfig_tweak_failure() -> None:
    b = NuttXBuilder(copy.deepcopy(conf_dir))
    b._find_kconfig_tweak = lambda _cwd: None
    with patch("ntfc.builder.logger.error") as error_mock:
        with pytest.raises(AssertionError, match="kconfig-tweak is required"):
            b._apply_kconfig_overrides_kconfig_tweak(
                "/tmp/.config", {"CONFIG_X": "y"}, "/tmp"
            )
    assert error_mock.called

    b._find_kconfig_tweak = lambda _cwd: "/usr/bin/kconfig-tweak"
    b._run_kconfig_tweak_cmd = lambda _cmd: (_ for _ in ()).throw(
        OSError("boom")
    )
    assert (
        b._apply_kconfig_overrides_kconfig_tweak(
            "/tmp/.config", {"CONFIG_X": "y"}, "/tmp"
        )
        is False
    )


def test_builder_run_kconfig_tweak_cmd() -> None:
    b = NuttXBuilder(copy.deepcopy(conf_dir))
    calls = []

    with patch("ntfc.builder.subprocess.run") as run_mock:
        run_mock.side_effect = lambda cmd, check: calls.append((cmd, check))
        b._run_kconfig_tweak_cmd(["kconfig-tweak", "--help"])

    assert calls == [(["kconfig-tweak", "--help"], True)]


def test_builder_log_kconfig_overrides() -> None:
    b = NuttXBuilder(copy.deepcopy(conf_dir))
    logs = []

    with patch("ntfc.builder.logger.info", side_effect=logs.append):
        b._log_kconfig_overrides({})
        b._log_kconfig_overrides({"CONFIG_A": "y", "CONFIG_B": 10})

    assert logs[0] == "Applying Kconfig overrides before build:"
    assert "CONFIG_A = y" in logs[1]
    assert "CONFIG_B = 10" in logs[2]


def test_builder_apply_kconfig_overrides() -> None:
    b = NuttXBuilder(copy.deepcopy(conf_dir))

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / ".config"
        cfg_path.write_text(
            "CONFIG_KEEP=y\n"
            "CONFIG_REPLACE=old\n"
            "# CONFIG_DISABLE_ME is not set\n",
            encoding="utf-8",
        )

        b._apply_kconfig_overrides(str(cfg_path), {})
        assert cfg_path.read_text(encoding="utf-8").startswith(
            "CONFIG_KEEP=y\n"
        )

        before_invalid = cfg_path.read_text(encoding="utf-8")
        b._apply_kconfig_overrides(str(cfg_path), {})
        assert cfg_path.read_text(encoding="utf-8") == before_invalid

        b._apply_kconfig_overrides(
            str(cfg_path),
            {
                "CONFIG_REPLACE": "newval",
                "CONFIG_DISABLE_ME": "y",
                "CONFIG_APPEND": "0x10",
                "CONFIG_OFF": False,
            },
        )

        cfg_text = cfg_path.read_text(encoding="utf-8")
        assert 'CONFIG_REPLACE="newval"\n' in cfg_text
        assert "CONFIG_DISABLE_ME=y\n" in cfg_text
        assert "CONFIG_APPEND=0x10\n" in cfg_text
        assert "# CONFIG_OFF is not set\n" in cfg_text
        assert "CONFIG_KEEP=y\n" in cfg_text

        missing_path = Path(tmpdir) / "missing.config"
        b._apply_kconfig_overrides(str(missing_path), {"CONFIG_X": "y"})


def test_builder_apply_kconfig_overrides_fallback_when_tool_fails() -> None:
    b = NuttXBuilder(copy.deepcopy(conf_dir))

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / ".config"
        cfg_path.write_text("# CONFIG_X is not set\n", encoding="utf-8")

        b._apply_kconfig_overrides_kconfig_tweak = lambda *_args: False
        with pytest.raises(
            AssertionError, match="failed to apply 'kv' build overrides"
        ):
            b._apply_kconfig_overrides(
                str(cfg_path), {"CONFIG_X": "y"}, cfg_cwd=str(tmpdir)
            )
        assert (
            cfg_path.read_text(encoding="utf-8") == "# CONFIG_X is not set\n"
        )


def test_builder_apply_kconfig_overrides_returns_after_kconfig_tweak() -> None:
    b = NuttXBuilder(copy.deepcopy(conf_dir))

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / ".config"
        original = "CONFIG_X=n\n"
        cfg_path.write_text(original, encoding="utf-8")

        calls = []

        def fake_apply_with_tool(conf_path, valid_overrides, cfg_cwd):
            calls.append((conf_path, valid_overrides, cfg_cwd))
            return True

        b._apply_kconfig_overrides_kconfig_tweak = fake_apply_with_tool
        b._apply_kconfig_overrides(
            str(cfg_path), {"CONFIG_X": "y"}, cfg_cwd=str(tmpdir)
        )

        assert len(calls) == 1
        assert calls[0][1] == {"CONFIG_X": "y"}
        # file remains unchanged because the helper path handled it
        assert cfg_path.read_text(encoding="utf-8") == original


def test_builder_apply_kconfig_overrides_requires_kconfig_tweak_in_build_path() -> (  # noqa: E501
    None
):
    b = NuttXBuilder(copy.deepcopy(conf_dir))

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / ".config"
        cfg_path.write_text("CONFIG_X=n\n", encoding="utf-8")
        b._find_kconfig_tweak = lambda _cwd: None

        with patch("ntfc.builder.logger.error") as error_mock:
            with pytest.raises(
                AssertionError, match="kconfig-tweak is required"
            ):
                b._apply_kconfig_overrides(
                    str(cfg_path), {"CONFIG_X": "y"}, cfg_cwd=str(tmpdir)
                )
        assert error_mock.called


def test_builder_applies_kv_before_build() -> None:
    config = copy.deepcopy(conf_dir)

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_dir = root / "build"
        cwd = root / "ext"
        (cwd / "nuttx").mkdir(parents=True)

        config["config"]["build_dir"] = str(build_dir)
        config["config"]["cwd"] = str(cwd)
        config["config"]["kv"] = {
            "CONFIG_TEST_BOOL": "y",
            "CONFIG_TEST_STR": "hello",
            "CONFIG_TEST_GLOBAL_ONLY": "123",
        }
        config["product"]["cores"]["core0"]["defconfig"] = "dummy/path"
        config["product"]["cores"]["core0"]["kv"] = {
            "CONFIG_TEST_STR": "core-value",
            "CONFIG_TEST_CORE_ONLY": "m",
        }

        expected_build_path = build_dir / "product-xxx-dummy"
        expected_conf_path = expected_build_path / ".config"

        calls = []
        logs = []

        def run_command_capture(cmd, env):
            calls.append(cmd)
            if "--build" not in cmd:
                expected_build_path.mkdir(parents=True, exist_ok=True)
                expected_conf_path.write_text(
                    "# CONFIG_TEST_BOOL is not set\n" "CONFIG_TEST_STR=old\n",
                    encoding="utf-8",
                )
            else:
                cfg_text = expected_conf_path.read_text(encoding="utf-8")
                assert "CONFIG_TEST_BOOL=y\n" in cfg_text
                assert 'CONFIG_TEST_STR="core-value"\n' in cfg_text
                assert "CONFIG_TEST_GLOBAL_ONLY=123\n" in cfg_text
                assert "CONFIG_TEST_CORE_ONLY=m\n" in cfg_text

        b = NuttXBuilder(config)
        b._run_command = run_command_capture

        def fake_apply_with_tool(conf_path, overrides, _cfg_cwd):
            b._apply_kconfig_overrides(conf_path, overrides, cfg_cwd="")
            return True

        b._apply_kconfig_overrides_kconfig_tweak = fake_apply_with_tool

        with patch("ntfc.builder.logger.info", side_effect=logs.append):
            b.build_all()

        assert len(calls) == 3
        assert calls[0][0] == "cmake"
        assert calls[1][:2] == ["cmake", "--build"]
        assert calls[1][-2:] == ["--target", "olddefconfig"]
        assert calls[2][:2] == ["cmake", "--build"]
        assert any(
            "Applying Kconfig overrides before build:" == msg for msg in logs
        )


def test_builder_raises_when_build_dir_missing() -> None:
    config = copy.deepcopy(conf_dir)
    config["product"]["cores"]["core0"]["defconfig"] = "dummy/path"
    del config["config"]["build_dir"]
    b = NuttXBuilder(config)

    with pytest.raises(
        BuilderConfigError, match="not found build_dir in YAML configuration"
    ):
        b.build_all()


def test_builder_raises_when_cwd_missing() -> None:
    config = copy.deepcopy(conf_dir)
    config["product"]["cores"]["core0"]["defconfig"] = "dummy/path"
    del config["config"]["cwd"]
    b = NuttXBuilder(config)

    with pytest.raises(
        BuilderConfigError, match="not found cwd in YAML configuration"
    ):
        b.build_all()


def test_builder_flash_supports_elf_placeholder(tmp_path) -> None:
    image = tmp_path / "nuttx"
    image.write_bytes(b"elf")
    core = {
        "elf_path": str(image),
        "flash": "pxe-stage $IMAGE_ELF",
    }
    commands = []
    builder = NuttXBuilder(copy.deepcopy(conf_dir))
    builder._run_command = lambda command, env: commands.append(command)

    builder._flash_core("core0", {"core0": core})

    assert commands == [["pxe-stage", str(image)]]
