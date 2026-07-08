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

"""Regression test: CoredumpPlugin's trylast wrapper must exit before a
plain hookwrapper registered earlier, matching pluggy's registration-order
semantics (last-registered wrapper is outermost / exits last; trylast
forces innermost / exits first)."""

import textwrap

import pytest


def test_trylast_wrapper_exits_before_plain_wrapper(
    pytester: pytest.Pytester,
) -> None:
    """A trylast hookwrapper must run its post-yield code first, even
    though it is registered AFTER a plain hookwrapper.

    This mirrors the real bug: ``PytestConfigPlugin`` (plain
    hookwrapper, registered first / innermost) reboots the device on
    crash, while ``CoredumpPlugin`` (registered last / outermost) must
    collect the coredump before that reboot happens. Marking
    ``CoredumpPlugin``'s hook ``trylast=True`` forces it innermost so
    its post-yield collection always runs before the plain wrapper's
    post-yield reboot, regardless of registration order.
    """
    pytester.makeconftest(textwrap.dedent("""
            import pytest


            class PlainWrapperFirst:
                @pytest.hookimpl(hookwrapper=True)
                def pytest_runtest_makereport(self, item, call):
                    yield
                    if call.when == "call":
                        with open("order.log", "a") as f:
                            f.write("plain_first\\n")


            class TrylastWrapperLast:
                @pytest.hookimpl(hookwrapper=True, trylast=True)
                def pytest_runtest_makereport(self, item, call):
                    yield
                    if call.when == "call":
                        with open("order.log", "a") as f:
                            f.write("trylast_last\\n")


            def pytest_configure(config):
                # Registration order matches the real bug: the plain
                # wrapper (ptconfig) is registered first, the trylast
                # wrapper (CoredumpPlugin) is registered last.
                config.pluginmanager.register(PlainWrapperFirst())
                config.pluginmanager.register(TrylastWrapperLast())
            """))
    pytester.makepyfile("""
        def test_something():
            assert True
        """)
    # -p no:sugar: pytest-sugar's reporter replaces the standard "N
    # passed" summary line with its own progress-bar output whenever
    # stdout is a real TTY, which breaks assert_outcomes()'s parsing of
    # this inner session's result regardless of the outer session's own
    # outcome.
    result = pytester.runpytest("-p", "no:sugar")
    result.assert_outcomes(passed=1)

    order_log = pytester.path / "order.log"
    assert order_log.read_text().splitlines() == [
        "trylast_last",
        "plain_first",
    ]
