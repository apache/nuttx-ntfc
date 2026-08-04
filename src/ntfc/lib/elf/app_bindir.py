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

"""Kernel-mode application binary directory handler.

In kernel builds every application is a standalone ELF binary installed
to the target PATH, so the command name is the file name; entry points
are renamed to ``main`` and symbols like ``hello_main`` do not exist.
"""

import os
import re
from functools import cached_property
from typing import Collection, Iterator, List, Optional, Pattern, Set, Union

from ntfc.lib.elf.elf_parser import ElfParser

_MAIN_SUFFIX = "_main"


def _match_one(name: str, commands: List[str]) -> bool:
    """Match a single name against a list of command names."""
    if ".*" in name:
        regex = re.compile(name)
        return any(regex.fullmatch(cmd) for cmd in commands)
    return name in commands


def match_command(pattern: str, commands: List[str]) -> bool:
    """Match a cmd_check pattern against a list of command names.

    Accepts ``a|b`` alternatives and ``.*`` regex patterns. A trailing
    ``_main`` is stripped so flat-mode symbol markers (e.g.
    ``hello_main``) match the ``hello`` command.
    """
    return any(
        _match_one(name, commands)
        for alt in pattern.split("|")
        for name in (alt, alt.removesuffix(_MAIN_SUFFIX))
    )


def symbol_patterns(pattern: str) -> Iterator[Union[str, Pattern[str]]]:
    """Yield normalized ELF symbol patterns for a cmd_check expression."""
    for alternative in pattern.split("|"):
        symbol = (
            f"{alternative}{_MAIN_SUFFIX}"
            if "cmocka" in alternative
            else alternative
        )
        yield re.compile(symbol) if ".*" in symbol else symbol


def match_symbol(pattern: str, symbols: Collection[str]) -> bool:
    """Match a cmd_check expression against ELF symbol names."""
    for candidate in symbol_patterns(pattern):
        if isinstance(candidate, str):
            if candidate in symbols:
                return True
        elif any(candidate.search(symbol) for symbol in symbols):
            return True

    return False


class AppBinDir:
    """Application binary directory of a kernel-mode build."""

    #: sibling directory with the unstripped application binaries
    DEBUG_DIR_NAME = "bin_debug"

    def __init__(self, bindir: str, debug_bindir: Optional[str] = None):
        """Initialize application binary directory handler.

        :param bindir: directory with application binaries
        :param debug_bindir: unstripped binaries for symbol lookups,
                             the sibling ``bin_debug`` by default
        """
        self._bindir = bindir
        self._debug_bindir = debug_bindir or os.path.join(
            os.path.dirname(bindir), self.DEBUG_DIR_NAME
        )

    @staticmethod
    def _scan(dirpath: Optional[str]) -> List[ElfParser]:
        """Return a parser for every ELF file in a directory."""
        if not dirpath or not os.path.isdir(dirpath):
            return []

        parsers = []
        for name in sorted(os.listdir(dirpath)):
            try:
                parsers.append(ElfParser(os.path.join(dirpath, name)))
            except AttributeError:
                # not an ELF file, e.g. a script or a subdirectory
                continue

        return parsers

    @cached_property
    def commands(self) -> List[str]:
        """Return available command names (application file names)."""
        return [os.path.basename(p.elf_path) for p in self._scan(self._bindir)]

    @cached_property
    def _symbols(self) -> Set[str]:
        """Return the symbols defined by the debug application binaries."""
        return {
            symbol.name
            for parser in self._scan(self._debug_bindir)
            for symbol in parser.symbols
        }

    def has_command(self, pattern: str) -> bool:
        """Check if a command is available, see :func:`match_command`."""
        return match_command(pattern, self.commands)

    def has_symbol(self, pattern: str) -> bool:
        """Check symbols using cmd_check alternatives and regex syntax."""
        return match_symbol(pattern, self._symbols)
