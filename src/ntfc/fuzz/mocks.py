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

"""Board-constant mocking for --mock mode.

A board's ``include/board.h`` normally defines the concrete pin mappings and
geometry constants the arch drivers consume. When a peripheral is enabled on a
board that does not wire it, those constants are missing and the arch path
never compiles. This module reads the build errors and synthesises just those
*board-supplied* constants (identified by the ArchProfile's mockable
prefixes/suffixes), so the arch build path can be validated. CONFIG_*, type
names, and local variables are never mocked, so real code bugs still fail.
"""

import re
from typing import TYPE_CHECKING, Dict, Optional, Tuple

if TYPE_CHECKING:
    from pathlib import Path

    from ntfc.fuzz.profiles import ArchProfile

# error: 'GPIO_CAN2_RX' undeclared (...); did you mean 'GPIO_CAN2_RX_1'?
_UNDECLARED_RE = re.compile(
    r"error: '([A-Za-z_]\w*)' undeclared"
    r"(?:[^\n;]*; did you mean '([A-Za-z_]\w*)'\?)?"
)

# #error BOARD_LTDC_WIDTH must be defined in the board.h header file
_MUSTDEF_RE = re.compile(r"#error\s+\"?([A-Z_][A-Z0-9_]*) must be defined")


def parse_mock_defines(
    log: str,
    existing: Dict[str, str],
    prefixes: Tuple[str, ...],
    suffixes: Tuple[str, ...] = (),
) -> Dict[str, str]:
    """Return the new board constants to define, given a build log.

    Only identifiers starting with one of ``prefixes`` or ending with one of
    ``suffixes`` are considered board-supplied and mockable. For an undeclared
    constant, use gcc's "did you mean" suggestion when it is an alternative of
    the same symbol (e.g. ``GPIO_CAN2_RX`` -> ``GPIO_CAN2_RX_1``); otherwise
    define it to 0. "must be defined" geometry constants get 1.
    """

    def mockable(name: str) -> bool:
        return name.startswith(prefixes) or name.endswith(suffixes)

    new: Dict[str, str] = {}
    for m in _UNDECLARED_RE.finditer(log):
        name, suggest = m.group(1), m.group(2)
        if not mockable(name) or name in existing or name in new:
            continue
        if suggest and suggest.startswith(name):
            new[name] = suggest
        else:
            new[name] = "0"
    for m in _MUSTDEF_RE.finditer(log):
        name = m.group(1)
        if not mockable(name) or name in existing or name in new:
            continue
        new[name] = "1"
    return new


def missing_board_constants(
    log: str,
    profile: "ArchProfile",
    existing: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Mock the board constants a build log needs, per the profile."""
    return parse_mock_defines(
        log,
        existing or {},
        profile.mockable_prefixes,
        profile.mockable_suffixes,
    )


def append_mock_defines(config_h: "Path", defines: Dict[str, str]) -> None:
    """Write a block of ``#define``s to the build's generated nuttx/config.h.

    config.h is force-included by every translation unit and lives in the build
    directory, so this injects the mocks without touching any source file.
    """
    if not defines:
        return
    lines = ["", "/* ntfc fuzz: mocked board constants */"]
    for name in sorted(defines):
        lines.append(f"#define {name} {defines[name]}")
    lines.append("")
    with config_h.open("a") as f:
        f.write("\n".join(lines))
