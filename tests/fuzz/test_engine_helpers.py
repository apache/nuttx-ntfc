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

import os
from pathlib import Path
from types import SimpleNamespace

from ntfc.fuzz.campaign import load_fuzz_config
from ntfc.fuzz.candidate import PASS, Outcome
from ntfc.fuzz.engine import (
    _build_root,
    _features_from_surface,
    _subsets,
    _surface_names,
    plan_candidates,
    run_mem,
)

BUILD = "tests/fuzz/resources/campaign-build.yaml"
MEM = "tests/fuzz/resources/campaign-mem.yaml"
OSTEST = "tests/fuzz/resources/campaign-ostest.yaml"


def test_subsets_single():
    assert _subsets({"mode": "single"}, ["A", "B"]) == [
        frozenset({"A"}),
        frozenset({"B"}),
    ]


def test_subsets_random_is_seeded():
    a = _subsets(
        {"mode": "random", "rounds": 4, "size": 2, "seed": 7}, ["A", "B", "C"]
    )
    assert len(a) == 4


def test_subsets_systematic():
    subs = _subsets({"mode": "marginal"}, ["A", "B"])
    assert frozenset({"A", "B"}) in subs


def test_build_root_is_under_build_dir():
    # bound at import time, before the conftest fixture patches it out
    assert _build_root("bd") == os.path.join("bd", "fuzz")


def test_subsets_limit_caps_candidates():
    subs = _subsets({"mode": "single", "limit": 2}, ["A", "B", "C"])
    assert subs == [frozenset({"A"}), frozenset({"B"})]


def test_plan_candidates_build_sweeps_discovered_surface():
    fuzz = load_fuzz_config(BUILD)
    fuzz.strategy["limit"] = 1

    def fake_discover(root, board, profile, selector, include_choices=False):
        return [
            SimpleNamespace(name="STM32_ADC1"),
            SimpleNamespace(name="STM32_ADC2"),
        ]

    subs = plan_candidates(fuzz, discover_fn=fake_discover)
    assert subs == [frozenset({"CONFIG_STM32_ADC1"})]


def test_plan_candidates_mem_starts_with_baseline():
    subs = plan_candidates(load_fuzz_config(MEM))
    assert subs[0] == frozenset()
    assert frozenset({"CONFIG_FS_FAT"}) in subs
    assert frozenset({"CONFIG_FS_FAT", "CONFIG_CRYPTO"}) in subs


def test_plan_candidates_ostest_baseline_and_skip():
    fuzz = load_fuzz_config(OSTEST)
    subs = plan_candidates(fuzz)
    assert subs[0] == frozenset()
    assert len(subs) == 7  # baseline + 6 random rounds

    fuzz.strategy["skip_baseline"] = True
    subs = plan_candidates(fuzz)
    assert len(subs) == 6
    assert frozenset() not in subs


def test_surface_names_features_flattens():
    fuzz = load_fuzz_config(BUILD)
    fuzz.surface = {"features": {"net": ["CONFIG_NET", "CONFIG_NETDEV"]}}
    names = _surface_names(fuzz, Path("."), None, "sim:nsh", None)
    assert set(names) == {"CONFIG_NET", "CONFIG_NETDEV"}


def test_features_from_surface_group():
    feats, req = _features_from_surface(
        {"features": {"net": ["CONFIG_NET", "CONFIG_NETDEV"]}},
        ["CONFIG_SCHED_HPWORK"],
    )
    assert feats[0].name == "net"
    assert req == frozenset({"CONFIG_SCHED_HPWORK"})


def test_mem_max_builds_cap():
    c = load_fuzz_config(MEM)
    c.strategy["mode"] = "full"
    c.strategy["max_builds"] = 1

    def build(builder, board_config, configs, build_dir, **kw):
        return Outcome(
            frozenset(configs), PASS, elf_path=os.path.join(build_dir, "nuttx")
        )

    report = run_mem(
        c,
        build_fn=build,
        size_fn=lambda e, size_tool="size": (10000, 200, 500),
    )
    assert report.memory == []
