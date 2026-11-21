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

"""ELF file parser for LTP test case extraction.

Used during test collection phase without fixture dependencies
"""

import logging
import os
import re
import subprocess
from typing import Dict, List, Pattern, Set, Tuple, Union


class Symbol:
    """ELF symbol representation."""

    def __init__(self, name: str, address: str = "", symbol_type: str = ""):
        """Initialize ELF symbol representation."""
        self.name = name
        self.address = address
        self.type = symbol_type


class ElfParser:
    """ELF file parser for extracting symbols."""

    _PREFIX_ANCHORS = {"nx_start", "main"}

    def __init__(self, elf_path: str):
        """Initialize ELF file parser."""
        if not os.path.exists(elf_path) or not self._is_elf_file(elf_path):
            raise AttributeError("can't load ELF file")

        self.elf_path = elf_path
        self._symbols: List[Symbol] = []

    def _is_elf_file(self, path: str) -> bool:
        """Check if this is ELF file."""
        try:
            with open(path, "rb") as f:
                magic = f.read(4)
            return magic == b"\x7fELF"
        except Exception:  # pragma: no cover
            return False

    @property
    def symbols(self) -> List[Symbol]:
        """Get all symbols from ELF file."""
        if not self._symbols:
            self._symbols = self._extract_symbols()
        return self._symbols

    def _extract_symbols(self) -> List[Symbol]:
        """Extract symbols using nm command."""
        try:
            result = subprocess.run(
                ["nm", "--defined-only", self.elf_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )

            entries: List[Tuple[str, Dict[str, str]]] = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue  # pragma: no cover

                parts = line.split()
                if len(parts) >= 3:
                    address, symbol_type, name = parts[0], parts[1], parts[2]
                    kwargs = {"address": address, "symbol_type": symbol_type}
                    entries.append((name, kwargs))
                elif len(parts) >= 2:
                    symbol_type, name = parts[0], parts[1]
                    entries.append((name, {"symbol_type": symbol_type}))
                elif len(parts) == 1:  # pragma: no cover
                    name = parts[0]
                    entries.append((name, {}))

            prefix = self._label_prefix({name for name, _ in entries})
            return [
                Symbol(name.removeprefix(prefix), **kwargs)
                for name, kwargs in entries
            ]

        except subprocess.CalledProcessError as e:  # pragma: no cover
            logging.error(
                f"Failed to extract symbols from {self.elf_path}: {e}"
            )
            return []

        except Exception as e:  # pragma: no cover
            logging.error(f"Unexpected error parsing ELF symbols: {e}")
            return []

    @classmethod
    def _label_prefix(cls, names: Set[str]) -> str:
        """Return "_" if the target prefixes C symbols, else ""."""
        prefixed = {"_" + a for a in cls._PREFIX_ANCHORS}
        if not names.isdisjoint(cls._PREFIX_ANCHORS):
            return ""
        return "_" if not names.isdisjoint(prefixed) else ""

    def get_symbols_by_pattern(
        self, prefix: str = "", suffix: str = ""
    ) -> List[Symbol]:
        """Filter symbols by prefix and suffix."""
        return [
            s
            for s in self.symbols
            if s.name.startswith(prefix) and s.name.endswith(suffix)
        ]

    def has_symbol(self, symbol_name: Union[str, Pattern[str]]) -> bool:
        """Check if symbol exists."""
        if isinstance(symbol_name, str):
            return any(symbol.name == symbol_name for symbol in self.symbols)

        if isinstance(symbol_name, re.Pattern):
            return any(
                symbol_name.search(symbol.name) for symbol in self.symbols
            )
        raise ValueError("symbol_name must be either str or re.Pattern")
