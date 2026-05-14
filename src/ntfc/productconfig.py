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

"""Product configuration handler."""

from typing import Any, Dict, List

from ntfc.coreconfig import CoreConfig
from ntfc.log.logger import logger


class ProductConfig:
    """Product configuration."""

    def __init__(self, cfg: Dict[str, Any]) -> None:
        """Initialzie product configuration."""
        self._config = cfg

        # Get platform type (amp or smp), default to amp
        self._platform: str = self._config.get("platform", "amp").lower()

        # Use dictionary to store cores, key is core name from config
        self._cores: Dict[str, CoreConfig] = {}
        self._core_index_to_name: Dict[int, str] = {}
        self._init_cores()

    def _init_cores(self) -> None:
        """Initialize cores dictionary from configuration."""
        cores_config = self.cores
        if not cores_config:
            return

        # Iterate through all coreX entries in config
        for core_key, core_data in cores_config.items():
            if not core_key.startswith("core") or not isinstance(
                core_data, dict
            ):
                continue

            # Parse index from "coreX" key
            try:
                core_index = int(core_key[4:])
            except (ValueError, IndexError):
                logger.warning(f"Invalid core key: {core_key}")
                continue

            # Get core name from config; fall back to "main"/"cpuN"
            core_name: str = core_data.get("name", "")
            if not core_name:
                core_name = "main" if core_index == 0 else f"cpu{core_index}"

            # Store CoreConfig and index→name mapping
            self._cores[core_name] = CoreConfig(core_data)
            self._core_index_to_name[core_index] = core_name

    @property
    def config(self) -> Any:
        """Return test configuration."""
        return self._config

    @property
    def cores(self) -> Any:
        """Return product cores configuration."""
        try:
            return self._config["cores"]
        except KeyError:
            logger.error("no cores info in configuration file!")
            return {}

    @property
    def name(self) -> str:
        """Get product name."""
        try:
            return str(self._config["name"])
        except KeyError:  # pragma: no cover
            logger.error("no product name in configuration file!")
            return "unknown_name"

    def _get_core_name(self, core: int | str) -> str:
        """Convert core parameter to core name.

        :param core: Core index (0, 1, 2) or name ('main', 'cpu1', 'cpu2')
        :return: Core name
        """
        if isinstance(core, str):
            return core

        if isinstance(core, int):
            return self._core_index_to_name.get(
                core, "main" if core == 0 else f"cpu{core}"
            )

        raise TypeError(f"core must be int or str, got {type(core)}")

    def kv_check(self, cfg: str, core: int | str = 0) -> Any:
        """Check Kconfig option.

        :param cfg: Kconfig option name
        :param core: Core index (0, 1, 2) or name ('main', 'cpu1', 'cpu2')
        """
        core_name = self._get_core_name(core)
        if core_name not in self._cores:
            raise AttributeError(f"no data for core '{core}'")

        return self._cores[core_name].kv_check(cfg)

    def core(self, cpu: int = 0) -> Dict[str, Any]:
        """Return core parameters."""
        if cpu == 0:
            cpuname = "core0"
        else:
            cpuname = "core" + str(cpu)

        result = self.cores.get(cpuname, "")
        return result if isinstance(result, dict) else {}

    def cmd_check(self, cmd: str, core: int | str = 0) -> bool:
        """Check if command is available in binary.

        :param cmd: Command name or pattern (e.g., 'free' or 'free|ps')
        :param core: Core index (0, 1, 2) or name ('main', 'cpu1', 'cpu2')
        """
        core_name = self._get_core_name(core)
        if core_name not in self._cores:
            raise AttributeError(f"no data for core '{core}'")

        return self._cores[core_name].cmd_check(cmd)

    @property
    def cores_num(self) -> int:
        """Get number of cores."""
        return len(self._cores)

    @property
    def core_names(self) -> list[str]:
        """Get list of all configured core names."""
        return list(self._cores.keys())

    @property
    def active_core_indices(self) -> list[int]:
        """Return configured core indices that participate in tests."""
        return [
            idx
            for idx in sorted(self._core_index_to_name)
            if not self.cfg_core(idx).flash_only
        ]

    @property
    def active_core_names(self) -> list[str]:
        """Return core names that participate in tests."""
        return [self._get_core_name(idx) for idx in self.active_core_indices]

    @property
    def active_cores_num(self) -> int:
        """Get number of cores that participate in tests."""
        return len(self.active_core_indices)

    @property
    def primary_test_core_index(self) -> int:
        """Return the default core index used for requirement checks."""
        active = self.active_core_indices
        return active[0] if active else 0

    def cfg_core(self, cpu: int) -> CoreConfig:
        """Get core configuration by index.

        :param cpu: Core index (0, 1, 2, ...)
        :return: CoreConfig instance
        """
        core_name = self._get_core_name(cpu)
        if core_name not in self._cores:
            raise AttributeError(f"no data for core index {cpu}")
        return self._cores[core_name]

    def cfg_core_by_name(self, name: str) -> CoreConfig:
        """Get core configuration by name.

        :param name: Core name ('main', 'cpu1', 'cpu2', ...)
        :return: CoreConfig instance
        """
        if name not in self._cores:
            raise AttributeError(f"no data for core '{name}'")
        return self._cores[name]

    @property
    def platform(self) -> str:
        """Get platform type (amp or smp)."""
        return self._platform

    @property
    def is_smp(self) -> bool:
        """Check if platform is SMP."""
        return self._platform == "smp"

    @property
    def is_amp(self) -> bool:
        """Check if platform is AMP."""
        return self._platform == "amp"

    @property
    def ignored_cores(self) -> List[str]:
        """Return list of core names to ignore when collecting core info.

        Configurable via ``ignored_cores`` key in the product YAML section.
        Defaults to ``["dsp"]``.
        """
        return list(self._config.get("ignored_cores", ["dsp"]))
