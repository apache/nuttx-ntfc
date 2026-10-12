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

"""Tests for the resource monitor."""

from typing import Dict, List

import pytest

from ntfc.resmon.monitor import ResourceLeakError, ResourceMonitor
from ntfc.resmon.probes import make_probes

FREE_HDR = (
    "      total       used       free    maxused    maxfree  nused  nfree"
    " name\n"
)
FREE_A = FREE_HDR + "   1000   100   900   100   900   6   3 Umem\n"
FREE_B = FREE_HDR + "   1000   116   884   116   884   7   3 Umem\n"


class FakeTarget:
    """Scripted command responder: returns outputs in sequence per cmd."""

    def __init__(self, script: Dict[str, List[str]]) -> None:
        self.script = script
        self.calls: List[str] = []

    def __call__(self, cmd: str) -> str:
        self.calls.append(cmd)
        outputs = self.script[cmd]
        return outputs.pop(0) if len(outputs) > 1 else outputs[0]


def _monitor(
    script: Dict[str, List[str]], retries: int = 3, delay: float = 1.0
) -> tuple[ResourceMonitor, FakeTarget, List[float]]:
    target = FakeTarget(script)
    sleeps: List[float] = []
    mon = ResourceMonitor(
        make_probes(["heap"], {}),
        {"p/main": target},
        settle_retries=retries,
        settle_delay=delay,
        sleep=sleeps.append,
    )
    return mon, target, sleeps


class TestResourceMonitor:
    def test_clean_check_returns_empty(self) -> None:
        mon, target, sleeps = _monitor({"free": [FREE_A]})
        mon.baseline()
        assert mon.check() == {}
        assert target.calls == ["free", "free"]
        assert sleeps == []

    def test_leak_raises_with_details(self) -> None:
        mon, _, _ = _monitor({"free": [FREE_A, FREE_B]}, retries=0)
        mon.baseline()
        with pytest.raises(ResourceLeakError) as exc:
            mon.check()
        msg = str(exc.value)
        assert "p/main" in msg
        assert "heap" in msg
        assert "Umem used 100 -> 116 (+16)" in msg

    def test_last_diff_kept_after_leak(self) -> None:
        mon, _, _ = _monitor({"free": [FREE_A, FREE_B]}, retries=0)
        mon.baseline()
        with pytest.raises(ResourceLeakError):
            mon.check()
        assert mon.last_diff == {
            "p/main": {
                "heap": [
                    "Umem used 100 -> 116 (+16)",
                    "Umem nused 6 -> 7 (+1)",
                ]
            }
        }

    def test_settle_clears_transient_delta(self) -> None:
        mon, target, sleeps = _monitor(
            {"free": [FREE_A, FREE_B, FREE_A]}, retries=3, delay=0.5
        )
        mon.baseline()
        assert mon.check() == {}
        assert target.calls == ["free"] * 3
        assert sleeps == [0.5]

    def test_retries_exhausted(self) -> None:
        mon, target, sleeps = _monitor(
            {"free": [FREE_A, FREE_B]}, retries=2, delay=0.1
        )
        mon.baseline()
        with pytest.raises(ResourceLeakError):
            mon.check()
        # baseline + first sample + 2 retries
        assert len(target.calls) == 4
        assert sleeps == [0.1, 0.1]

    def test_check_without_baseline(self) -> None:
        mon, _, _ = _monitor({"free": [FREE_A]})
        with pytest.raises(RuntimeError, match="baseline"):
            mon.check()

    def test_inactive_without_probes(self) -> None:
        target = FakeTarget({"free": [FREE_A]})
        mon = ResourceMonitor([], {"p/main": target})
        assert mon.active is False
        mon.baseline()
        assert mon.check() == {}
        assert target.calls == []

    def test_inactive_without_targets(self) -> None:
        mon = ResourceMonitor(make_probes(["heap"], {}), {})
        assert mon.active is False

    def test_active(self) -> None:
        mon, _, _ = _monitor({"free": [FREE_A]})
        assert mon.active is True

    def test_snapshot_exposes_parsed_values(self) -> None:
        mon, _, _ = _monitor({"free": [FREE_A]})
        snap = mon.snapshot()
        assert snap["p/main"]["heap"]["Umem"]["used"] == 100

    def test_multi_command_probe_feeds_all_outputs(self) -> None:
        target = FakeTarget(
            {
                "cat /proc/net/tcp": ["TCP sl\n 0: x 1.1.1.1:1 2.2.2.2:2\n"],
                "cat /proc/net/udp": ["UDP sl\n"],
            }
        )
        mon = ResourceMonitor(make_probes(["net"], {}), {"t": target})
        mon.baseline()
        assert mon.check() == {}
        assert target.calls[:2] == ["cat /proc/net/tcp", "cat /proc/net/udp"]
