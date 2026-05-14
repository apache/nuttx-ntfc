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

"""Configuration handler."""

from typing import Any, Dict, List

from ntfc.productconfig import ProductConfig


class EnvConfig:
    """This class handles tests environment configuration."""

    def __init__(self, config: Dict[str, Any], _args: Any = None) -> None:
        """Initialzie tests environment configuration."""
        if not isinstance(config, dict):
            raise TypeError("invalid config file type")

        self._args: List[Any] = []
        self._cfg_values = {}

        self._cfg_values = config

        self._products = self._products_create(self._cfg_values)

    def _products_create(self, config: Dict[str, Any]) -> List[ProductConfig]:
        """Create product configuration."""
        products = []
        for k in config.keys():
            if "product" in k:
                p = ProductConfig(config[k])
                products.append(p)

        return products

    @property
    def common(self) -> Any:
        """Return device parameters."""
        return self._cfg_values.get("config", {})

    @property
    def product(self) -> list[Any]:
        """Return product instance."""
        return self._products

    def product_get(self, product: int = 0) -> Any:
        """Return product parameters."""
        if product >= len(self._products):
            return None
        return self._products[product].config

    def core(self, product: int = 0, cpu: int = 0) -> Dict[str, Any]:
        """Return core parameters."""
        if product >= len(self._products):
            return {}
        tmp = self._products[product].core(cpu)
        if not tmp:
            return {}
        return tmp

    @property
    def config(self) -> Dict[str, Any]:
        """Return test configuration."""
        return self._cfg_values

    @property
    def heartbeat(self) -> Dict[str, Any]:
        """Return heartbeat monitoring configuration.

        :return: Dictionary with keys: 'enabled' (bool), 'interval' (int),
            'threshold' (int). Defaults to disabled if not configured.
        """
        default_config = {
            "enabled": False,
            "interval": 60,
            "threshold": 3,
        }
        config = self._cfg_values.get("config", {})
        heartbeat_cfg = config.get("heartbeat", {})

        # Merge with defaults
        return {**default_config, **heartbeat_cfg}

    @property
    def recovery(self) -> Dict[str, Any]:
        """Return device recovery configuration.

        :return: Dictionary with keys: 'max_retries' (int),
            'base_delay' (float), 'reboot_timeout' (int).
            Defaults to 3 retries, 2s base delay, 30s reboot timeout.
        """
        default_config = {
            "max_retries": 3,
            "base_delay": 2.0,
            "reboot_timeout": 30,
        }
        config = self._cfg_values.get("config", {})
        recovery_cfg = config.get("recovery", {})

        return {**default_config, **recovery_cfg}

    # dep_config
    def kv_check(
        self, cfg: str, product: int = 0, core: int | str | None = None
    ) -> Any:
        """Check Kconfig option.

        :param cfg: Kconfig option name
        :param product: Product index (default: 0)
        :param core: Core index/name to check. When omitted, uses the primary
            non-``flash_only`` core for the selected product.
        """
        if core is None:
            core = self._products[product].primary_test_core_index
        return self._products[product].kv_check(cfg, core)

    def cmd_check(
        self, cmd: str, product: int = 0, core: int | str | None = None
    ) -> bool:
        """Check if command is available in binary.

        :param cmd: Command name or pattern (e.g., 'free' or 'free|ps')
        :param product: Product index (default: 0)
        :param core: Core index/name to check. When omitted, uses the primary
            non-``flash_only`` core for the selected product.
        """
        if core is None:
            core = self._products[product].primary_test_core_index
        return self._products[product].cmd_check(cmd, core)

    def extra_check(
        self, _extra: str, _product: int = 0, _core: int = 0
    ) -> bool:
        """Check for extra options."""
        if "run_in_core" in _extra:
            return True

        # not supported yet
        return False
