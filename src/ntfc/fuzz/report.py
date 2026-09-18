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

"""Fuzz run reporting: categorized text + JSON, written to the session dir."""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from ntfc.fuzz.candidate import STATUSES, Outcome


def _label(configs: FrozenSet[str]) -> str:
    return "baseline" if not configs else "{" + ",".join(sorted(configs)) + "}"


@dataclass
class FuzzReport:
    """Collects candidate outcomes and renders text / JSON reports."""

    base: str
    feature: str
    outcomes: List[Outcome] = field(default_factory=list)
    baseline: Optional[Outcome] = None
    minimized: List[Tuple[Outcome, FrozenSet[str]]] = field(
        default_factory=list
    )
    memory: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, outcome: Outcome) -> None:
        """Record one candidate outcome."""
        self.outcomes.append(outcome)

    def counts(self) -> Dict[str, int]:
        """Return per-status counts across all outcomes."""
        c = {s: 0 for s in STATUSES}
        for o in self.outcomes:
            c[o.status] = c.get(o.status, 0) + 1
        return c

    def failed(self) -> bool:
        """Whether any candidate did not pass (natively or mocked)."""
        return any(not o.ok for o in self.outcomes)

    def _outcome_dict(self, o: Outcome) -> Dict[str, Any]:
        return {
            "configs": sorted(o.configs),
            "status": o.status,
            "detail": o.detail,
            "log_path": o.log_path,
            "mocks": o.mocks,
        }

    def json(self) -> Dict[str, Any]:
        """Return the report as a JSON-serialisable dictionary."""
        return {
            "base": self.base,
            "feature": self.feature,
            "counts": self.counts(),
            "baseline": (
                self._outcome_dict(self.baseline)
                if self.baseline is not None
                else None
            ),
            "outcomes": [self._outcome_dict(o) for o in self.outcomes],
            "minimized": [
                {"original": sorted(o.configs), "minimal": sorted(m)}
                for o, m in self.minimized
            ],
            "memory": self.memory,
        }

    def text(self) -> str:  # noqa: C901
        """Return a human-readable text report."""
        out: List[str] = []
        out.append(f"[fuzz:{self.feature}] base {self.base}")
        if self.baseline is not None:
            det = f" ({self.baseline.detail})" if self.baseline.detail else ""
            out.append(f"[fuzz] baseline: {self.baseline.status}{det}")
        counts = self.counts()
        out.append(
            "[fuzz] outcomes: "
            + ", ".join(f"{s}={counts[s]}" for s in STATUSES)
        )
        out.append("")

        fails = [o for o in self.outcomes if not o.ok]
        if fails:
            out.append("failing candidates:")
            for o in fails:
                line = f"  {_label(o.configs):<44} {o.status}"
                if o.detail:
                    line += f"  ({o.detail})"
                if o.log_path:
                    line += f"  {o.log_path}"
                out.append(line)
            out.append("")
        if self.minimized:
            out.append("minimised failures (delta-debug):")
            for o, m in self.minimized:
                out.append(f"  {_label(o.configs)} -> {_label(m)}")
            out.append("")
        if self.memory:
            out.append("memory (flash/ram delta vs baseline):")
            for row in self.memory:
                out.append(
                    f"  {row['feature']:<32} "
                    f"flash {row['flash_delta']:+d}  ram {row['ram_delta']:+d}"
                )
            out.append("")
        if not fails and not self.memory:
            out.append("all candidates passed.")
        return "\n".join(out)

    def write(self, session_dir: str) -> None:
        """Write ``fuzz-report.txt`` and ``fuzz-report.json`` to the dir."""
        os.makedirs(session_dir, exist_ok=True)
        with open(
            os.path.join(session_dir, "fuzz-report.txt"), "w", encoding="utf-8"
        ) as f:
            f.write(self.text() + "\n")
        with open(
            os.path.join(session_dir, "fuzz-report.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(self.json(), f, indent=2)
