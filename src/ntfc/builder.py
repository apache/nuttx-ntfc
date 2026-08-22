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

"""Build manager for NuttX configuration."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ntfc.log.logger import logger


class BuilderConfigError(ValueError):
    """Invalid build configuration in YAML."""


class NuttXBuilder:
    """NuttX configuration builder (CMake only)."""

    IMAGE_BIN_STR = "$IMAGE_BIN"
    IMAGE_HEX_STR = "$IMAGE_HEX"
    IMAGE_ELF_STR = "$IMAGE_ELF"
    _KCONFIG_DISABLED_RE = re.compile(
        r"^#\s+(CONFIG_[A-Za-z0-9_]+)\s+is not set"
    )

    def __init__(self, config: Dict[str, Any], rebuild: bool = True):
        """Initialize NuttX builder."""
        if not isinstance(config, dict):
            raise TypeError("invalid config file type")

        self._cfg_values = config
        self._rebuild = rebuild

    def _run_command(
        self, cmd: List[str], env: Any
    ) -> None:  # pragma: no cover
        """Run command."""
        subprocess.run(cmd, check=True, env=env)

    def _make_dir(self, path: Path) -> None:
        """Create dir."""
        os.makedirs(path, exist_ok=True)

    def _get_build_env(self, core_cfg: Dict[str, Any]) -> Dict[str, str]:
        """Collect build environment variables for a core.

        Supports YAML fields:
        - config.build_env: shared env for all builds
        - <product>.cores.<core>.build_env: per-core overrides
        """
        build_env: Dict[str, str] = {}

        global_env = self._cfg_values.get("config", {}).get("build_env", {})
        if isinstance(global_env, dict):
            build_env.update(
                {str(key): str(val) for key, val in global_env.items()}
            )

        core_env = core_cfg.get("build_env", {})
        if isinstance(core_env, dict):
            build_env.update(
                {str(key): str(val) for key, val in core_env.items()}
            )

        return build_env

    def _get_cmake_defines(
        self, core_cfg: Dict[str, Any], build_cfg: str
    ) -> Dict[str, str]:
        """Collect CMake defines for a core.

        YAML syntax is a mapping:
        - dcmake: { KEY: VALUE }
        """
        defines = {"BOARD_CONFIG": build_cfg}
        custom_defines = core_cfg.get("dcmake", {})

        if isinstance(custom_defines, dict):
            defines.update(
                {str(key): str(val) for key, val in custom_defines.items()}
            )

        apps_dir = self._cfg_values.get("config", {}).get("apps_dir")
        if apps_dir:
            defines["NUTTX_APPS_DIR"] = os.path.abspath(
                os.path.expanduser(os.path.expandvars(str(apps_dir)))
            )

        return defines

    def _get_kconfig_overrides(
        self, core_cfg: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Collect Kconfig overrides from global and per-core YAML.

        Precedence:
        - ``config.kv`` (global defaults)
        - ``<product>.cores.<core>.kv`` (per-core overrides)
        """
        merged: Dict[str, Any] = {}

        global_kv = self._cfg_values.get("config", {}).get("kv", {})
        merged.update(self._valid_kconfig_overrides(global_kv))

        if core_cfg is not None:
            core_kv = core_cfg.get("kv", {})
            merged.update(self._valid_kconfig_overrides(core_kv))

        return merged

    def _valid_kconfig_overrides(self, overrides: Any) -> Dict[str, Any]:
        """Normalize Kconfig overrides to ``{CONFIG: value}`` mapping.

        Preferred syntax is a mapping. Legacy list-of-pairs is still accepted.
        """
        valid_overrides: Dict[str, Any] = {}

        if isinstance(overrides, dict):
            valid_overrides.update(
                {
                    str(key): value
                    for key, value in overrides.items()
                    if isinstance(key, str)
                }
            )
            return valid_overrides

        if isinstance(overrides, list):
            for item in overrides:
                if (
                    isinstance(item, list)
                    and len(item) == 2
                    and isinstance(item[0], str)
                ):
                    valid_overrides[item[0]] = item[1]

        return valid_overrides

    def _find_kconfig_tweak(self, _cfg_cwd: str) -> Optional[str]:
        """Find ``kconfig-tweak`` tool in PATH."""
        return shutil.which("kconfig-tweak")

    def _run_kconfig_tweak_cmd(self, cmd: List[str]) -> None:
        """Run one ``kconfig-tweak`` command."""
        subprocess.run(cmd, check=True)

    def _build_kconfig_tweak_cmd(
        self, tool: str, conf_path: str, key: str, value: Any
    ) -> List[str]:
        """Build one ``kconfig-tweak`` command for a Kconfig override."""
        cmd = [tool, "--file", conf_path]
        if value is False or value == "n":
            cmd.extend(["--disable", key])
        elif value is True or value == "y":
            cmd.extend(["--enable", key])
        elif value == "m":
            cmd.extend(["--module", key])
        elif isinstance(value, int):
            cmd.extend(["--set-val", key, str(value)])
        elif isinstance(value, str):
            if value.startswith('"') and value.endswith('"'):
                cmd.extend(["--set-str", key, value[1:-1]])
            elif value.startswith("0x") or value.isdigit():
                cmd.extend(["--set-val", key, value])
            else:
                cmd.extend(["--set-str", key, value])
        else:
            cmd.extend(["--set-str", key, str(value)])

        return cmd

    def _apply_kconfig_overrides_kconfig_tweak(
        self, conf_path: str, valid_overrides: Dict[str, Any], cfg_cwd: str
    ) -> bool:
        """Apply overrides with ``kconfig-tweak`` if available."""
        tool = self._find_kconfig_tweak(cfg_cwd)
        if not tool:
            logger.error(
                "kconfig-tweak is required to apply 'kv' configuration "
                "overrides during build. Install it and ensure it is in PATH."
            )
            raise AssertionError(
                "kconfig-tweak is required for 'kv' build overrides"
            )

        for key, value in valid_overrides.items():
            cmd = self._build_kconfig_tweak_cmd(tool, conf_path, key, value)

            try:
                self._run_kconfig_tweak_cmd(cmd)
            except (OSError, subprocess.CalledProcessError):
                return False

        return True

    def _format_kconfig_line(self, key: str, value: Any) -> str:
        """Format one Kconfig assignment/comment line."""
        if value is False:
            return f"# {key} is not set\n"

        if value is True:
            return f"{key}=y\n"

        if isinstance(value, int):
            return f"{key}={value}\n"

        if isinstance(value, str):
            if value == "n":
                return f"# {key} is not set\n"
            if value in ("y", "m"):
                return f"{key}={value}\n"
            if value.startswith('"') and value.endswith('"'):
                return f"{key}={value}\n"
            if value.startswith("0x") or value.isdigit():
                return f"{key}={value}\n"
            return f'{key}="{value}"\n'

        return f'{key}="{value}"\n'

    def _apply_kconfig_overrides(
        self, conf_path: str, overrides: Dict[str, Any], cfg_cwd: str = ""
    ) -> None:
        """Apply Kconfig overrides to generated ``.config``."""
        if not overrides:
            return

        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:  # pragma: no cover
            return

        if cfg_cwd:
            ok = self._apply_kconfig_overrides_kconfig_tweak(
                conf_path, overrides, cfg_cwd
            )
            assert (
                ok
            ), "failed to apply 'kv' build overrides with kconfig-tweak"
            return

        replaced: set[str] = set()
        updated_lines: List[str] = []
        for line in lines:
            replaced_line = self._replace_kconfig_line(
                line, overrides, replaced, updated_lines
            )
            if not replaced_line:
                updated_lines.append(line)

        for key, value in overrides.items():
            if key not in replaced:
                updated_lines.append(self._format_kconfig_line(key, value))

        with open(conf_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)

    def _replace_kconfig_line(
        self,
        line: str,
        overrides: Dict[str, Any],
        replaced: set[str],
        updated_lines: List[str],
    ) -> bool:
        """Replace one existing Kconfig line if it matches an override."""
        disabled_match = self._KCONFIG_DISABLED_RE.match(line)

        for key, value in overrides.items():
            if line.startswith(f"{key}=") or (
                disabled_match and disabled_match.group(1) == key
            ):
                updated_lines.append(self._format_kconfig_line(key, value))
                replaced.add(key)
                return True

        return False

    def _log_kconfig_overrides(self, overrides: Dict[str, Any]) -> None:
        """Log Kconfig override list at build start."""
        if not overrides:
            return

        logger.info("Applying Kconfig overrides before build:")
        for key, value in overrides.items():
            logger.info(f"  {key} = {value}")

    def _run_cmake(
        self,
        source: str,
        build: str,
        generator: str = "Ninja",
        defines: Optional[Dict[str, str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        """Run CMake configure step."""
        build_path = Path(build)
        self._make_dir(build_path)

        # base command
        cmd = [
            "cmake",
            f"-B{build}",
            f"-S{source}",
            f"-G{generator}",
        ]

        # add -DVAR=value parameters
        if defines:  # pragma: no cover
            for k, v in defines.items():
                cmd.append(f"-D{k}={v}")

        # merge environment variables
        run_env = os.environ.copy()
        if env:
            run_env.update(env)  # pragma: no cover

        self._run_command(cmd, env=run_env)

    def _run_build(
        self, build: str, env: Optional[Dict[str, str]] = None
    ) -> None:
        """Run the CMake build step."""
        build_path = Path(build)

        cmd = [
            "cmake",
            "--build",
            str(build_path),
        ]

        run_env = os.environ.copy()
        if env:
            run_env.update(env)  # pragma: no cover

        self._run_command(cmd, env=run_env)

    def _run_build_target(
        self,
        build: str,
        target: str,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        """Run one named CMake build target."""
        cmd = ["cmake", "--build", str(Path(build)), "--target", target]
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        self._run_command(cmd, env=run_env)

    def _build_core(
        self, core: str, cores: Dict[str, Any], product: str
    ) -> None:
        """Build single core image."""
        if "defconfig" in cores[core]:
            build_dir = (
                product
                + "-"
                + self._cfg_values[product]["name"]
                + "-"
                + cores[core]["name"]
            )

            cfg_build_dir = self._cfg_values["config"].get("build_dir", None)
            if not cfg_build_dir:  # pragma: no cover
                raise BuilderConfigError(
                    "not found build_dir in YAML configuration"
                )

            cfg_cwd = self._cfg_values["config"].get("cwd", None)
            if not cfg_cwd:  # pragma: no cover
                raise BuilderConfigError("not found cwd in YAML configuration")

            cfg_build_dir = os.path.expanduser(
                os.path.expandvars(str(cfg_build_dir))
            )
            build_path = os.path.join(cfg_build_dir, build_dir)
            build_cfg = cores[core]["defconfig"]
            logger.info(
                f"build image " f"conf: {build_cfg}, out: {build_path}"
            )

            cfg_cwd = os.path.expanduser(os.path.expandvars(str(cfg_cwd)))
            configured_nuttx_dir = self._cfg_values["config"].get("nuttx_dir")
            nuttx_dir = (
                os.path.expanduser(
                    os.path.expandvars(str(configured_nuttx_dir))
                )
                if configured_nuttx_dir
                else os.path.join(cfg_cwd, "nuttx")
            )
            nuttx_elf_path = os.path.join(build_path, "nuttx")
            nuttx_conf_path = os.path.join(build_path, ".config")

            already_build = False
            if os.path.isfile(nuttx_elf_path) and os.path.isfile(
                nuttx_conf_path
            ):
                already_build = True  # pragma: no cover

            # get defines passed to cmake
            defines = self._get_cmake_defines(cores[core], build_cfg)

            build_env = self._get_build_env(cores[core])
            kv_overrides = self._get_kconfig_overrides(cores[core])

            if not already_build or self._rebuild:  # pragma: no cover
                self._log_kconfig_overrides(kv_overrides)

                # configure build
                self._run_cmake(
                    source=nuttx_dir,
                    build=build_path,
                    generator="Ninja",
                    defines=defines,
                    env=build_env,
                )

                # apply Kconfig overrides to generated .config before build
                self._apply_kconfig_overrides(
                    nuttx_conf_path, kv_overrides, cfg_cwd
                )

                # Regenerate include/nuttx/config.h after changing .config.
                # Otherwise CMake can relink an image built with stale Kconfig
                # values while the saved .config claims the override applied.

                if kv_overrides:
                    self._run_build_target(
                        build_path, "olddefconfig", env=build_env
                    )

                # build
                self._run_build(build_path, env=build_env)

            # add elf and conf path
            cores[core]["elf_path"] = nuttx_elf_path
            cores[core]["conf_path"] = nuttx_conf_path

    def _reboot_core(
        self, core: str, cores: Dict[str, Any]
    ) -> None:  # pragma: no cover
        """Reboot single core."""
        reboot_cmd = cores[core].get("reboot", None)
        if reboot_cmd:
            cmd = reboot_cmd.split()
            logger.info(f"reboot core cmd: {cmd}")
            self._run_command(cmd, env=None)

    def _flash_core(
        self, core: str, cores: Dict[str, Any]
    ) -> None:  # pragma: no cover
        """Flash single core image."""
        flash_cmd = cores[core].get("flash", None)
        if flash_cmd:
            img_path = Path(cores[core]["elf_path"])
            image_hex = str(img_path.parent) + "/nuttx.hex"
            image_bin = str(img_path.parent) + "/nuttx.bin"

            flash_cmd = flash_cmd.replace(self.IMAGE_BIN_STR, image_bin)
            flash_cmd = flash_cmd.replace(self.IMAGE_HEX_STR, image_hex)
            flash_cmd = flash_cmd.replace(self.IMAGE_ELF_STR, str(img_path))

            cmd = flash_cmd.split()

            logger.info(f"flash image cmd: {cmd}")
            self._run_command(cmd, env=None)

    def need_build(self) -> bool:
        """Check if we need build something."""
        for product in self._cfg_values:
            if "product" in product:
                cores = self._cfg_values[product]["cores"]
                for core in cores:
                    if cores[core].get("defconfig", None):
                        return True
        return False

    def build_all(self) -> None:
        """Build all defconfigs from configuration file."""
        for product in self._cfg_values:
            if "product" in product:
                cores = self._cfg_values[product]["cores"]
                for core in cores:
                    self._build_core(core, cores, product)

    def flash_all(self) -> None:
        """Flash all available images."""
        for product in self._cfg_values:
            if "product" in product:
                cores = self._cfg_values[product]["cores"]
                for core in cores:
                    # flash core image
                    self._flash_core(core, cores)
                    # reboot after flash
                    self._reboot_core(core, cores)

    def new_conf(self) -> Dict[str, Any]:
        """Get modified YAML config."""
        return self._cfg_values
