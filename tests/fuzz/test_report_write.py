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

import json
import os

from ntfc.fuzz.candidate import BUILD_FAIL, PASS, PASS_MOCKED, Outcome
from ntfc.fuzz.report import FuzzReport


def test_write_emits_txt_and_json(tmp_path):
    r = FuzzReport(base="sim:ntfc", feature="build")
    r.add(Outcome(frozenset({"CONFIG_A"}), PASS))
    r.add(Outcome(frozenset({"CONFIG_B"}), BUILD_FAIL, "boom", log_path="x"))
    r.write(str(tmp_path))

    assert os.path.exists(tmp_path / "fuzz-report.txt")
    with open(tmp_path / "fuzz-report.json", encoding="utf-8") as f:
        data = json.load(f)
    assert data["feature"] == "build"
    assert len(data["outcomes"]) == 2
    assert data["counts"][PASS] == 1
    assert data["counts"][BUILD_FAIL] == 1


def test_text_lists_failures_and_baseline():
    r = FuzzReport(base="sim:ntfc", feature="ostest")
    r.baseline = Outcome(frozenset(), PASS)
    r.add(Outcome(frozenset({"CONFIG_B"}), BUILD_FAIL, "boom"))
    r.minimized.append(
        (
            Outcome(frozenset({"CONFIG_B", "CONFIG_C"}), BUILD_FAIL),
            frozenset({"CONFIG_B"}),
        )
    )
    text = r.text()
    assert "baseline: pass" in text
    assert "failing candidates:" in text
    assert "minimised failures" in text


def test_text_failure_without_detail():
    r = FuzzReport(base="sim:ntfc", feature="build")
    r.add(Outcome(frozenset({"CONFIG_B"}), BUILD_FAIL))  # no detail, no log
    text = r.text()
    assert "CONFIG_B" in text
    assert "failing candidates:" in text


def test_text_all_passed():
    r = FuzzReport(base="sim:ntfc", feature="build")
    r.add(Outcome(frozenset({"CONFIG_A"}), PASS))
    assert "all candidates passed." in r.text()
    assert r.failed() is False


def test_pass_mocked_counts_as_ok():
    r = FuzzReport(base="sim:ntfc", feature="build")
    r.add(Outcome(frozenset({"CONFIG_A"}), PASS_MOCKED))
    assert r.failed() is False


def test_memory_rows_rendered():
    r = FuzzReport(base="sim:ntfc", feature="mem")
    r.memory.append(
        {"feature": "CONFIG_FS_FAT", "flash_delta": 2000, "ram_delta": 0}
    )
    text = r.text()
    assert "memory (flash/ram delta" in text
    assert "CONFIG_FS_FAT" in text
