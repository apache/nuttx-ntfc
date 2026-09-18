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

import pytest
import yaml

from ntfc.fuzz.campaign import CampaignError, load_fuzz_config
from ntfc.fuzz.candidate import BUILD_FAIL, CRASH, PASS, Outcome
from ntfc.fuzz.engine import run_campaign, run_ostest

OSTEST = "tests/fuzz/resources/campaign-ostest.yaml"
TARGET = "tests/fuzz/resources/target-sim.yaml"


def _target():
    with open(TARGET, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _pass_build(builder, board_config, configs, build_dir, **kw):
    return Outcome(configs, PASS, elf_path=build_dir + "/nuttx")


def _crash_if_bad_run(core_conf, configs, patterns, timeout, **kwargs):
    if "CONFIG_BAD" in configs:
        return Outcome(configs, CRASH, "assert")
    return Outcome(configs, PASS)


def test_ostest_sweep_minimizes_to_culprit():
    c = load_fuzz_config(OSTEST)
    report = run_ostest(
        c, _target(), build_fn=_pass_build, run_fn=_crash_if_bad_run
    )
    data = report.json()
    assert data["baseline"]["status"] == PASS
    assert data["base"] == "sim:nsh"
    mins = data["minimized"]
    assert mins
    assert all("CONFIG_BAD" in m["minimal"] for m in mins)


def test_ostest_build_fail_short_circuits_run():
    c = load_fuzz_config(OSTEST)
    c.strategy["minimize"] = False
    c.strategy["skip_baseline"] = True

    def failing_build(builder, board_config, configs, build_dir, **kw):
        return Outcome(configs, BUILD_FAIL, "boom")

    def must_not_run(*a, **k):
        raise AssertionError("run must not happen when build fails")

    report = run_ostest(
        c, _target(), build_fn=failing_build, run_fn=must_not_run
    )
    assert all(o.status == BUILD_FAIL for o in report.outcomes)


def test_ostest_baseline_build_fail_aborts_sweep():
    c = load_fuzz_config(OSTEST)

    def failing_build(builder, board_config, configs, build_dir, **kw):
        return Outcome(configs, BUILD_FAIL, "no nuttx tree")

    def must_not_run(*a, **k):
        raise AssertionError("nothing should run if the baseline won't build")

    report = run_ostest(
        c, _target(), build_fn=failing_build, run_fn=must_not_run
    )
    assert report.baseline.status == BUILD_FAIL
    assert report.outcomes == []


def test_ostest_build_fails_are_not_minimized():
    c = load_fuzz_config(OSTEST)
    c.strategy["skip_baseline"] = True
    c.strategy["minimize"] = True

    def build(builder, board_config, configs, build_dir, **kw):
        if len(configs) > 1:
            return Outcome(configs, BUILD_FAIL, "boom")
        return Outcome(configs, PASS, elf_path=build_dir + "/nuttx")

    def run(core_conf, configs, patterns, timeout, **kwargs):
        return Outcome(configs, PASS)

    report = run_ostest(c, _target(), build_fn=build, run_fn=run)
    assert report.minimized == []


def test_ostest_skip_baseline():
    c = load_fuzz_config(OSTEST)
    c.strategy["skip_baseline"] = True
    c.strategy["minimize"] = False
    report = run_ostest(
        c, _target(), build_fn=_pass_build, run_fn=_crash_if_bad_run
    )
    assert report.baseline is None


def test_ostest_scope_surface_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("feature: ostest\nsurface: {scope: [net]}\n")
    c = load_fuzz_config(str(p))
    with pytest.raises(CampaignError, match="symbols"):
        run_ostest(c, _target(), build_fn=_pass_build)


def test_run_campaign_dispatches_ostest():
    c = load_fuzz_config(OSTEST)
    c.strategy["minimize"] = False
    report = run_campaign(
        c, _target(), build_fn=_pass_build, run_fn=_crash_if_bad_run
    )
    assert report.feature == "ostest"


def test_run_campaign_ostest_without_target_raises():
    c = load_fuzz_config(OSTEST)
    with pytest.raises(CampaignError, match="target"):
        run_campaign(c, None)
