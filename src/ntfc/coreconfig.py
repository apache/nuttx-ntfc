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

"""Product core configuration handler."""

from typing import Any, Dict, Optional, Union

from ntfc.lib.elf.elf_parser import ElfParser


class CoreConfig:
    """Product core configuration."""

    def __init__(self, cfg: Dict[str, Any]) -> None:
        """Initialzie product core configuration."""
        self._config = cfg

        self._kv_values: Dict[str, Any] = {}
        self._elf: Optional[ElfParser] = None

        conf_path = self._config.get("conf_path", None)
        if conf_path:
            # load config values
            self._load_core_config()

        elf_path = self._config.get("elf_path", None)
        if elf_path:
            # load ELF
            self._elf = ElfParser(elf_path)

    def _load_core_config(self) -> None:
        """Load core configuration."""
        with open(self._config["conf_path"], "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                # ignore blank lines and commented lines
                if not line or line.startswith("#"):
                    continue

                name, sep, val = line.partition("=")
                if not sep:
                    # no '=' found — skip malformed line
                    continue

                # parse option value
                val_parsed: Union[bool, str, int]
                if val == "y":
                    val_parsed = True
                elif val == "n":
                    val_parsed = False
                elif "0x" in val:
                    val_parsed = int(val.rstrip(), 16)
                elif val.isdigit():
                    val_parsed = int(val)
                elif val.startswith('"') and val.endswith('"'):
                    val_parsed = val[1:-1]
                else:
                    val_parsed = val

                self._kv_values[name] = val_parsed

    @property
    def uptime(self) -> Any:
        """Return core uptime."""
        return self._config.get("uptime", 3)

    @property
    def device(self) -> Any:
        """Return core device."""
        return self._config.get("device", None)

    @property
    def name(self) -> Any:
        """Return core name."""
        return self._config.get("name", "unknown_name")

    def _load_prompt_from_config(self) -> Optional[str]:
        """Load the prompt string from the .config file."""
        return self._kv_values.get("CONFIG_NSH_PROMPT_STRING", None)

    @property
    def prompt(self) -> Any:
        """Return core prompt.

        First check YAML config, if not present, load from .config file.
        """
        # First check if prompt is explicitly set in YAML config
        yaml_prompt = self._config.get("prompt", None)
        if yaml_prompt:
            return yaml_prompt

        # Otherwise, load from .config file
        return self._load_prompt_from_config()

    @property
    def elf_path(self) -> Any:
        """Return core elf path."""
        return self._config.get("elf_path", "")

    @property
    def exec_path(self) -> Any:
        """Return core exec path."""
        return self._config.get("exec_path", "")

    @property
    def exec_args(self) -> Any:
        """Return core exec args."""
        return self._config.get("exec_args", "")

    @property
    def reboot(self) -> Any:
        """Return core reboot command."""
        return self._config.get("reboot", "")

    @property
    def poweroff(self) -> Any:
        """Return core poweroff command."""
        return self._config.get("poweroff", "")

    @property
    def flash_only(self) -> bool:
        """Return whether this core is build/flash-only.

        Flash-only cores are still built/flashed by NTFC, but are skipped for
        runtime test orchestration: no boot checks, no log collection, no test
        requirements validation, and no command execution against them.
        """
        return bool(self._config.get("flash_only", False))

    def kv_check(self, cfg: str) -> Any:
        """Check Kconfig option and return its value.

        :param cfg: Kconfig option name (e.g., 'CONFIG_DEBUG')
        :return: Config value if set (bool True, string value, etc),
                 False if not found
        """
        if not self._kv_values:
            # No config data loaded
            return False

        return self._kv_values.get(cfg, False)

    def cmd_check(self, cmd: str, core: int = 0) -> bool:
        """Check if command is available in binary."""
        if not self._elf:
            raise AttributeError("no elf data")

        symbol_name = f"{cmd}_main" if "cmocka" in cmd else cmd
        return self._elf.has_symbol(symbol_name)
