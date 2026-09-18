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

"""Linked-image size measurement for the memory-footprint fuzz mode.

Parses ``size <elf>`` (Berkeley format) into ``(text, data, bss)`` and derives
flash/RAM: ``flash = text + data``, ``ram = data + bss``. This is the static
footprint of the linked image; it does not model runtime heap or stack.
"""

import subprocess
from typing import Tuple


def elf_size(elf_path: str, size_tool: str = "size") -> Tuple[int, int, int]:
    """Return ``(text, data, bss)`` for an ELF, or zeros if size fails."""
    try:
        r = subprocess.run(
            [size_tool, elf_path], text=True, capture_output=True
        )
    except OSError:
        return (0, 0, 0)
    if r.returncode != 0:
        return (0, 0, 0)
    rows = [ln for ln in r.stdout.splitlines() if ln.strip()]
    if len(rows) < 2:
        return (0, 0, 0)
    parts = rows[1].split()
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return (0, 0, 0)


def footprint(text: int, data: int, bss: int) -> Tuple[int, int]:
    """Return ``(flash, ram)`` from section sizes."""
    return (text + data, data + bss)
