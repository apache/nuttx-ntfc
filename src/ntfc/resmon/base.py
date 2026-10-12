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

"""Resource probe base classes and output parsing helpers."""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

_LINE_END_RE = re.compile(r"\r*\n")

###############################################################################
# Function: clean_output
###############################################################################


def clean_output(raw: str, cmd: str, prompt: str) -> str:
    """Strip the echoed command and the trailing prompt from NSH output.

    :param raw: Output as returned by the device.
    :param cmd: Command that was sent.
    :param prompt: Target shell prompt.
    :return: Output lines with normalized line endings.
    """
    text = _LINE_END_RE.sub("\n", raw).replace("\r", "")
    lines = text.split("\n")
    # leading stale prompts and the echo, with or without its prompt
    echo = {cmd.strip(), prompt.strip() + " " + cmd.strip(), prompt.strip()}
    while lines and lines[0].strip() in echo:
        lines = lines[1:]
    if lines and lines[-1].strip() == prompt.strip():
        lines[-1] = ""
    return "\n".join(lines)


###############################################################################
# Function: parse_table
###############################################################################


def find_header(lines: List[str], required: Sequence[str]) -> Optional[int]:
    """Return the index of the first line naming every required column."""
    for idx, line in enumerate(lines):
        tokens = line.split()
        if all(col in tokens for col in required):
            return idx
    return None


def parse_table(
    text: str,
    columns: Optional[List[str]] = None,
    skip: int = 0,
    required: Optional[Sequence[str]] = None,
) -> List[Dict[str, str]]:
    """Parse a whitespace separated table into rows keyed by column name.

    The last column absorbs the rest of the line, so values with spaces
    (for example a task command line) are kept intact. Short rows are
    padded with empty strings.

    :param text: Table text.
    :param columns: Column names. When omitted the header line provides
     them.
    :param skip: Number of leading non-empty lines to drop.
    :param required: Column names that identify the header line. Lines
     before it (for example shell diagnostics) are ignored; without a
     matching line the table is empty.
    :return: List of rows.
    """
    lines = [line for line in text.split("\n") if line.strip()][skip:]
    if required is not None:
        header = find_header(lines, required)
        if header is None:
            return []
        lines = lines[header:]
    if columns is None:
        if not lines:
            return []
        columns = lines[0].split()
        lines = lines[1:]
    elif required is not None:
        lines = lines[1:]

    rows = []
    for line in lines:
        parts = [p.strip() for p in line.split(None, len(columns) - 1)]
        parts += [""] * (len(columns) - len(parts))
        rows.append(dict(zip(columns, parts)))
    return rows


###############################################################################
# Class: Probe
###############################################################################


class Probe(ABC):
    """One resource sampled before and after a test."""

    name = ""
    commands: Tuple[str, ...] = ()
    kconfig: Tuple[Tuple[str, bool], ...] = ()

    def __init__(self, options: Mapping[str, Any]) -> None:
        """Initialize probe.

        :param options: Resource monitor configuration.
        """
        self._options = options

    @abstractmethod
    def parse(self, outputs: List[str]) -> Any:
        """Parse command outputs, one per entry in :attr:`commands`."""

    @abstractmethod
    def diff(self, before: Any, after: Any) -> List[str]:
        """Compare two parsed samples.

        :return: Human readable leak descriptions, empty when clean.
        """


###############################################################################
# Class: CounterProbe
###############################################################################


class CounterProbe(Probe):
    """Numeric table probe: rows keyed by a column, counters compared."""

    key_column: Optional[str] = None
    # column -> option holding the allowed growth, None for zero tolerance
    grow_columns: Dict[str, Optional[str]] = {}
    shrink_columns: Tuple[str, ...] = ()

    def _required(self) -> Tuple[str, ...]:
        """Return the column names that identify the table header."""
        columns = (self.key_column, *self.grow_columns, *self.shrink_columns)
        return tuple(col for col in columns if col)

    def _rows(self, text: str) -> List[Dict[str, str]]:
        """Return table rows from the command output."""
        return parse_table(text, required=self._required())

    def _valid(self, text: str) -> bool:
        """Return True when the output contains the expected header."""
        lines = [line for line in text.split("\n") if line.strip()]
        return find_header(lines, self._required()) is not None

    def parse(self, outputs: List[str]) -> Dict[str, Dict[str, int]]:
        """Parse the table into ``{row key: {column: value}}``."""
        if not self._valid(outputs[0]):
            raise ValueError(f"{self.name}: unexpected output: {outputs[0]!r}")
        parsed = {}
        for row in self._rows(outputs[0]):
            key = row[self.key_column] if self.key_column else self.name
            parsed[key] = {
                col: int(val) for col, val in row.items() if val.isdigit()
            }
        return parsed

    def _tolerance(self, column: str) -> int:
        """Return the allowed growth for a column."""
        option = self.grow_columns[column]
        return int(self._options.get(option, 0)) if option else 0

    def diff(
        self,
        before: Dict[str, Dict[str, int]],
        after: Dict[str, Dict[str, int]],
    ) -> List[str]:
        """Report rows that appeared and counters that moved."""
        result = []
        for key, row in after.items():
            if key not in before:
                result.append(f"{key} new")
                continue
            for col in self.grow_columns:
                delta = row[col] - before[key][col]
                if delta > self._tolerance(col):
                    result.append(
                        f"{key} {col} {before[key][col]} -> {row[col]} "
                        f"({delta:+d})"
                    )
            for col in self.shrink_columns:
                delta = row[col] - before[key][col]
                if delta < 0:
                    result.append(
                        f"{key} {col} {before[key][col]} -> {row[col]} "
                        f"({delta:+d})"
                    )
        return result


###############################################################################
# Class: SetProbe
###############################################################################


class SetProbe(Probe):
    """Set probe: entries present after but not before are leaks."""

    key_columns: Tuple[str, ...] = ()

    def _entries(self, text: str) -> Set[Tuple[str, ...]]:
        """Return the entry keys from the command output."""
        return {
            tuple(row[col] for col in self.key_columns)
            for row in parse_table(text, required=self.key_columns)
        }

    def parse(self, outputs: List[str]) -> Set[Tuple[str, ...]]:
        """Parse all outputs into one set of entries."""
        entries: Set[Tuple[str, ...]] = set()
        for output in outputs:
            entries |= self._entries(output)
        return entries

    def diff(
        self, before: Set[Tuple[str, ...]], after: Set[Tuple[str, ...]]
    ) -> List[str]:
        """Report entries added since the baseline."""
        return [
            f"new {self.name}: {' '.join(entry)}"
            for entry in sorted(after - before)
        ]
