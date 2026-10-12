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

"""Resource monitor: baseline, settle and compare samples."""

import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ntfc.log.logger import logger

if TYPE_CHECKING:
    from .base import Probe

Sampler = Callable[[str], str]
Sample = Dict[str, Dict[str, Any]]
Diff = Dict[str, Dict[str, List[str]]]

###############################################################################
# Class: ResourceLeakError
###############################################################################


class ResourceLeakError(AssertionError):
    """Raised when resources were not released after a test."""


###############################################################################
# Class: ResourceMonitor
###############################################################################


class ResourceMonitor:
    """Sample probes on a set of targets and compare against a baseline.

    :param probes: Probes to run.
    :param targets: Mapping of target name to a callable that sends one
     NSH command and returns its cleaned output.
    :param settle_retries: Re-samples allowed while a delta remains.
    :param settle_delay: Seconds between re-samples.
    :param sleep: Sleep function, injectable for tests.
    """

    def __init__(
        self,
        probes: "List[Probe]",
        targets: Dict[str, Sampler],
        settle_retries: int = 3,
        settle_delay: float = 1.0,
        sleep: Callable[[float], Any] = time.sleep,
    ) -> None:
        """Initialize the monitor."""
        self._probes = probes
        self._targets = targets
        self._retries = settle_retries
        self._delay = settle_delay
        self._sleep = sleep
        self._baseline: Optional[Sample] = None
        self.last_diff: Diff = {}

    @property
    def active(self) -> bool:
        """Return True when there is something to sample."""
        return bool(self._probes) and bool(self._targets)

    def snapshot(self) -> Sample:
        """Sample every probe on every target."""
        sample: Sample = {}
        for target, send in self._targets.items():
            sample[target] = {
                probe.name: probe.parse([send(cmd) for cmd in probe.commands])
                for probe in self._probes
            }
        return sample

    def baseline(self) -> None:
        """Record the baseline sample."""
        self._baseline = self.snapshot() if self.active else {}

    def _diff(self, after: Sample) -> Diff:
        """Compare a sample against the baseline, keeping only leaks."""
        assert self._baseline is not None
        result: Diff = {}
        for target, probes in after.items():
            for probe in self._probes:
                lines = probe.diff(
                    self._baseline[target][probe.name], probes[probe.name]
                )
                if lines:
                    result.setdefault(target, {})[probe.name] = lines
        return result

    def check(self) -> Diff:
        """Re-sample until clean or retries run out.

        :return: Empty dict when clean.
        :raises RuntimeError: No baseline recorded.
        :raises ResourceLeakError: A delta remained after settling.
        """
        if self._baseline is None:
            raise RuntimeError("resource monitor has no baseline")
        if not self.active:
            return {}

        diff = self._diff(self.snapshot())
        for _ in range(self._retries):
            if not diff:
                break
            logger.debug(f"resources: delta remains, settling: {diff}")
            self._sleep(self._delay)
            diff = self._diff(self.snapshot())

        self.last_diff = diff
        if diff:
            raise ResourceLeakError(self.format_diff(diff))
        return diff

    @staticmethod
    def format_diff(diff: Diff) -> str:
        """Render a diff as one line per leak."""
        lines = []
        for target, probes in diff.items():
            for probe, items in probes.items():
                for item in items:
                    lines.append(f"{target} {probe}: {item}")
        return "resource leak detected:\n" + "\n".join(lines)
