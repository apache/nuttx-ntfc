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

"""Built-in resource probes."""

import re
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, Type

from .base import CounterProbe, Probe, SetProbe, find_header, parse_table

_PROCFS = ("CONFIG_FS_PROCFS", True)
_PROCESS = ("CONFIG_FS_PROCFS_EXCLUDE_PROCESS", False)
_CAT = ("CONFIG_NSH_DISABLE_CAT", False)

###############################################################################
# Class: HeapProbe
###############################################################################


class HeapProbe(CounterProbe):
    """Heap usage from ``free``."""

    name = "heap"
    commands = ("free",)
    kconfig = (
        _PROCFS,
        ("CONFIG_FS_PROCFS_EXCLUDE_MEMINFO", False),
        ("CONFIG_NSH_DISABLE_FREE", False),
    )
    key_column = "name"
    grow_columns = {"used": "heap_tolerance", "nused": None}


###############################################################################
# Class: TasksProbe
###############################################################################


class TasksProbe(SetProbe):
    """Tasks and threads from ``ps``."""

    name = "tasks"
    commands = ("ps",)
    kconfig = (_PROCFS, _PROCESS, ("CONFIG_NSH_DISABLE_PS", False))

    def _entries(self, text: str) -> Set[Tuple[str, ...]]:
        """Key tasks by TID and command line.

        Columns such as EVENT can be blank, so the command is taken from
        the header offset of ``COMMAND`` rather than by splitting.
        """
        lines = [line for line in text.split("\n") if line.strip()]
        header = find_header(lines, ("TID", "COMMAND"))
        if header is None:
            return set()
        start = lines[header].index("COMMAND")
        return {
            (line.split()[0], line[start:].strip())
            for line in lines[header + 1 :]
        }


###############################################################################
# Class: FdsProbe
###############################################################################


class FdsProbe(SetProbe):
    """File descriptors open in the shell task group."""

    name = "fds"
    commands = ("cat /proc/self/group/fd",)
    kconfig = (_PROCFS, _PROCESS, _CAT)
    key_columns = ("FD", "TYPE", "PATH")


###############################################################################
# Class: IobProbe
###############################################################################


class IobProbe(CounterProbe):
    """Network I/O buffer pool from ``/proc/iobinfo``."""

    name = "iob"
    commands = ("cat /proc/iobinfo",)
    kconfig = (
        _PROCFS,
        _CAT,
        ("CONFIG_MM_IOB", True),
        ("CONFIG_FS_PROCFS_EXCLUDE_IOBINFO", False),
    )
    shrink_columns = ("nfree",)


###############################################################################
# Class: MempoolProbe
###############################################################################


class MempoolProbe(CounterProbe):
    """Memory pools from ``/proc/mempool``."""

    name = "mempool"
    commands = ("cat /proc/mempool",)
    kconfig = (
        _PROCFS,
        _CAT,
        ("CONFIG_MM_HEAP_MEMPOOL", True),
        ("CONFIG_FS_PROCFS_EXCLUDE_MEMPOOL", False),
    )
    key_column = "name"
    grow_columns = {"nused": None}
    _COLUMNS = [
        "name",
        "total",
        "bsize",
        "nused",
        "nfree",
        "nifree",
        "nwaiter",
    ]

    def _required(self) -> Tuple[str, ...]:
        """Return the counter columns; the first header column is unnamed."""
        return ("nused", "nfree")

    def _rows(self, text: str) -> List[Dict[str, str]]:
        """Parse rows; the header has an unnamed first column."""
        rows = parse_table(
            text, columns=self._COLUMNS, required=self._required()
        )
        for row in rows:
            row["name"] = row["name"].rstrip(":")
        return rows


###############################################################################
# Class: NetProbe
###############################################################################


class NetProbe(SetProbe):
    """Socket connections from ``/proc/net/tcp`` and ``/proc/net/udp``."""

    name = "net"
    commands = ("cat /proc/net/tcp", "cat /proc/net/udp")
    kconfig = (
        _PROCFS,
        _CAT,
        ("CONFIG_NET", True),
        ("CONFIG_FS_PROCFS_EXCLUDE_NET", False),
    )

    def _entries(self, text: str) -> Set[Tuple[str, ...]]:
        """Key connections by local and remote endpoint."""
        entries: Set[Tuple[str, ...]] = set()
        for line in text.split("\n"):
            tokens = line.split()
            if len(tokens) >= 3 and tokens[0].endswith(":"):
                entries.add((tokens[-2], tokens[-1]))
        return entries


###############################################################################
# Class: CpuloadProbe
###############################################################################


class CpuloadProbe(Probe):
    """CPU load from ``/proc/cpuload`` checked against a limit."""

    name = "cpuload"
    commands = ("cat /proc/cpuload",)
    kconfig = (
        _PROCFS,
        _CAT,
        ("CONFIG_SCHED_CPULOAD", True),
        ("CONFIG_FS_PROCFS_EXCLUDE_CPULOAD", False),
    )
    _LOAD_RE = re.compile(r"([\d.]+)%")
    DEFAULT_MAX = 10.0

    def parse(self, outputs: List[str]) -> Optional[float]:
        """Return the load percentage, or ``None`` when unreadable."""
        match = self._LOAD_RE.search(outputs[0])
        return float(match.group(1)) if match else None

    def diff(
        self, before: Optional[float], after: Optional[float]
    ) -> List[str]:
        """Report a load above the configured limit."""
        del before
        limit = float(self._options.get("cpuload_max", self.DEFAULT_MAX))
        if after is None or after <= limit:
            return []
        return [f"cpuload {after:g}% > {limit:g}%"]


###############################################################################
# Registry
###############################################################################

PROBES: Dict[str, Type[Probe]] = {
    probe.name: probe
    for probe in (
        HeapProbe,
        TasksProbe,
        FdsProbe,
        IobProbe,
        MempoolProbe,
        NetProbe,
        CpuloadProbe,
    )
}


def make_probes(names: List[str], options: Mapping[str, Any]) -> List[Probe]:
    """Instantiate probes by name.

    :param names: Probe names in the order they should run.
    :param options: Resource monitor configuration.
    :raises ValueError: Unknown probe name.
    """
    probes = []
    for name in names:
        if name not in PROBES:
            raise ValueError(f"unknown resource probe: {name}")
        probes.append(PROBES[name](options))
    return probes
