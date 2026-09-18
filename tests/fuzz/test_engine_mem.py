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

from ntfc.fuzz.campaign import load_fuzz_config
from ntfc.fuzz.candidate import BUILD_FAIL, PASS, Outcome
from ntfc.fuzz.engine import run_campaign, run_mem

MEM = "tests/fuzz/resources/campaign-mem.yaml"


def test_mem_reports_positive_delta():
    c = load_fuzz_config(MEM)
    built = {}

    def fake_build(builder, board_config, configs, build_dir, **kw):
        built[build_dir] = frozenset(configs)
        return Outcome(
            frozenset(configs), PASS, elf_path=os.path.join(build_dir, "nuttx")
        )

    def fake_size(elf_path, size_tool="size"):
        cfgs = built.get(os.path.dirname(elf_path), frozenset())
        extra = 2000 if "CONFIG_FS_FAT" in cfgs else 0
        return (10000 + extra, 200, 500)

    report = run_mem(c, build_fn=fake_build, size_fn=fake_size)
    table = report.json()["memory"]
    fat = [r for r in table if r["feature"] == "CONFIG_FS_FAT"][0]
    assert fat["flash_delta"] == 2000
    assert fat["ram_delta"] == 0


def test_mem_baseline_build_fail_returns_empty():
    c = load_fuzz_config(MEM)

    def failing_build(builder, board_config, configs, build_dir, **kw):
        return Outcome(frozenset(configs), BUILD_FAIL, "boom")

    report = run_mem(c, build_fn=failing_build)
    assert report.memory == []
    assert report.baseline is not None
    assert report.baseline.status == BUILD_FAIL


def test_mem_variant_build_fail_skipped():
    c = load_fuzz_config(MEM)

    def build(builder, board_config, configs, build_dir, **kw):
        if "CONFIG_FS_FAT" in configs:
            return Outcome(frozenset(configs), BUILD_FAIL, "boom")
        return Outcome(
            frozenset(configs), PASS, elf_path=os.path.join(build_dir, "nuttx")
        )

    def size(elf_path, size_tool="size"):
        return (10000, 200, 500)

    report = run_mem(c, build_fn=build, size_fn=size)
    feats = {r["feature"] for r in report.memory}
    assert "CONFIG_FS_FAT" not in feats
    assert "CONFIG_CRYPTO" in feats
    # failed variants ({FS_FAT} and the all-on pair) are recorded in the
    # report, not silently dropped
    assert report.counts()[BUILD_FAIL] == 2
    assert report.failed() is True
    assert report.baseline is not None
    assert report.baseline.status == PASS


def test_run_campaign_dispatches_mem():
    c = load_fuzz_config(MEM)

    def build(builder, board_config, configs, build_dir, **kw):
        return Outcome(
            frozenset(configs), PASS, elf_path=os.path.join(build_dir, "nuttx")
        )

    report = run_campaign(
        c,
        None,
        build_fn=build,
        size_fn=lambda e, size_tool="size": (10000, 200, 500),
    )
    assert report.feature == "mem"
