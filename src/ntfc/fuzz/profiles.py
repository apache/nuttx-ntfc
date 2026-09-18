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

"""Architecture profiles for the Kconfig fuzzer.

All architecture-specific knowledge lives in an ``ArchProfile``: which Kconfig
symbols form the fuzz surface, which are never toggled, which build-error
identifiers are board-supplied (mockable), and which failures are
board-configuration requirements rather than code bugs. The profile data comes
from ``data/arch-profiles.yaml`` via :mod:`ntfc.fuzz.dataload`; this module
only defines the runtime object and the scope-selector compiler.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ArchProfile:
    """Rules describing one architecture's fuzz surface."""

    name: str
    symbol_path_re: "re.Pattern[str]"
    skip_prefixes: Tuple[str, ...]
    mockable_prefixes: Tuple[str, ...]
    mockable_suffixes: Tuple[str, ...] = field(default_factory=tuple)
    extra_board_required: Tuple[str, ...] = field(default_factory=tuple)
    generic_board_required: Tuple[str, ...] = field(default_factory=tuple)
    generic_config_required: Tuple[str, ...] = field(default_factory=tuple)

    def board_required_re(self) -> "re.Pattern[str]":
        """Patterns that mean a board-config prerequisite is unmet."""
        pats = list(self.generic_board_required) + list(
            self.extra_board_required
        )
        return re.compile("|".join(pats), re.IGNORECASE)

    def config_required_re(self) -> "re.Pattern[str]":
        """Patterns that mean a Kconfig dependency is unmet."""
        return re.compile(
            "|".join(self.generic_config_required), re.IGNORECASE
        )

    def is_arch_symbol(self, sym: object) -> bool:
        """Whether a kconfiglib symbol belongs to this arch's surface."""
        return any(
            self.symbol_path_re.search(n.filename or "")
            for n in sym.nodes  # type: ignore[attr-defined]
        )


def build_selector(
    profile: ArchProfile,
    scope_arg: Optional[str],
    scopes: Dict[str, str],
) -> "re.Pattern[str]":
    """Compile the symbol selector for a scope argument.

    ``None`` -> the arch profile's own surface. ``'arch'`` -> the arch surface;
    ``'all'`` -> everything; otherwise a comma-separated list of named scopes
    (e.g. ``'net,fs,audio'``) matched against a symbol's defining Kconfig file.
    """
    from ntfc.fuzz.dataload import FuzzDataError

    if not scope_arg:
        return profile.symbol_path_re
    pats: List[str] = []
    for name in (s.strip() for s in scope_arg.split(",")):
        if name == "all":
            return re.compile(".")
        if name == "arch":
            pats.append(profile.symbol_path_re.pattern)
        elif name in scopes:
            pats.append(scopes[name])
        else:
            known = ", ".join(["arch", "all"] + sorted(scopes))
            raise FuzzDataError(f"unknown scope '{name}'; known: {known}")
    return re.compile("|".join(pats))
