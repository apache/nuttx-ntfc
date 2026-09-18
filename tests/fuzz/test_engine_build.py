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

from ntfc.fuzz.campaign import load_fuzz_config
from ntfc.fuzz.candidate import BUILD_FAIL, PASS, Outcome
from ntfc.fuzz.engine import run_build, run_campaign
from ntfc.fuzz.model import SymbolInfo

BUILD = "tests/fuzz/resources/campaign-build.yaml"


def _fake_discover(*args, **kwargs):
    return [
        SymbolInfo("CAN1", "bool", "n", "y", ["drivers/can/Kconfig"], False),
        SymbolInfo("CAN2", "bool", "n", "y", ["drivers/can/Kconfig"], False),
    ]


def _fake_build(builder, board_config, configs, build_dir, **kwargs):
    if "CONFIG_CAN2" in configs:
        return Outcome(
            configs,
            BUILD_FAIL,
            "error: 'GPIO_CAN2_RX' undeclared",
            log_path="/tmp/build-CONFIG_CAN2.log",
        )
    return Outcome(configs, PASS)


def test_run_build_collects_outcomes():
    c = load_fuzz_config(BUILD)
    report = run_build(c, discover_fn=_fake_discover, build_fn=_fake_build)
    data = report.json()
    statuses = {o["status"] for o in data["outcomes"]}
    assert BUILD_FAIL in statuses
    assert PASS in statuses
    assert report.base == "sim:ntfc"
    fails = [o for o in data["outcomes"] if o["status"] == BUILD_FAIL]
    assert any("CONFIG_CAN2" in o["configs"] for o in fails)
    assert report.failed() is True


def test_run_build_symbols_surface_skips_discovery(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "feature: build\nboard: sim:nsh\ntree: .\n"
        "surface: {symbols: [CAN1, CAN2]}\n"
    )
    c = load_fuzz_config(str(p))

    def boom_discover(*a, **k):
        raise AssertionError("discovery must not run for symbols surface")

    report = run_build(c, discover_fn=boom_discover, build_fn=_fake_build)
    assert len(report.outcomes) == 2


def test_run_campaign_dispatches_build():
    c = load_fuzz_config(BUILD)
    report = run_campaign(
        c, None, discover_fn=_fake_discover, build_fn=_fake_build
    )
    assert report.feature == "build"
    assert len(report.outcomes) == 2


def test_run_build_sequential():
    c = load_fuzz_config(BUILD)
    c.parallel = False
    report = run_build(c, discover_fn=_fake_discover, build_fn=_fake_build)
    assert len(report.outcomes) == 2


def test_run_build_emits_progress():
    c = load_fuzz_config(BUILD)
    c.parallel = False
    msgs = []
    run_build(
        c,
        discover_fn=_fake_discover,
        build_fn=_fake_build,
        progress=msgs.append,
    )
    joined = "\n".join(msgs)
    assert "build sweep: 2 candidate(s)" in joined
    assert any("build-fail" in m and "GPIO_CAN2_RX" in m for m in msgs)
    assert any("log saved: /tmp/build-CONFIG_CAN2.log" in m for m in msgs)
    assert "build sweep complete" in joined
