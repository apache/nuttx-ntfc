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

from ntfc.fuzz import dataload
from ntfc.fuzz.candidate import (
    CRASH,
    PASS,
    TEST_FAIL,
    TIMEOUT,
    Outcome,
    classify_run,
)


def _pats():
    return dataload.load_patterns()


def test_classify_pass():
    status, detail = classify_run(
        "ostest_main: Exiting with status 0", 0, False, _pats()
    )
    assert status == PASS
    assert detail == ""


def test_classify_test_fail():
    status, detail = classify_run(
        "ostest_main: Exiting with status 3", 0, False, _pats()
    )
    assert status == TEST_FAIL
    assert "3" in detail


def test_classify_timeout():
    status, _ = classify_run("partial output", -1, True, _pats())
    assert status == TIMEOUT


def test_classify_crash_on_assert():
    status, _ = classify_run("up_assert: blah", 0, False, _pats())
    assert status == CRASH


def test_classify_crash_on_segfault():
    status, detail = classify_run("nothing useful", -11, False, _pats())
    assert status == CRASH
    assert "SIGSEGV" in detail


def test_classify_crash_when_no_completion():
    status, detail = classify_run("just booted", 0, False, _pats())
    assert status == CRASH
    assert "did not finish" in detail


def test_outcome_ok_property():
    assert Outcome(frozenset({"CONFIG_A"}), PASS).ok is True
    assert Outcome(frozenset({"CONFIG_A"}), CRASH).ok is False


def test_extract_errors_picks_error_lines():
    from ntfc.fuzz.candidate import extract_errors

    pats = _pats()
    log = (
        "compiling foo.c\n"
        "foo.c:12:3: error: 'GPIO_CAN2_RX' undeclared\n"
        "some noise\n"
        "ninja: error: build stopped\n"
    )
    out = extract_errors(log, pats)
    assert "GPIO_CAN2_RX" in out
    assert "ninja: error" in out
    assert "some noise" not in out


def test_extract_errors_falls_back_to_tail():
    from ntfc.fuzz.candidate import extract_errors

    pats = _pats()
    log = "line1\nline2\nline3\n"  # no error-pattern matches
    out = extract_errors(log, pats, max_lines=2)
    assert out == "line2\nline3"
