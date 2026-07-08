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

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from ntfc.pytest.coredump_plugin import CoredumpPlugin

if TYPE_CHECKING:
    from pathlib import Path


def _make_report(when: str = "call", failed: bool = True) -> MagicMock:
    r = MagicMock()
    r.when = when
    r.failed = failed
    return r


def _make_outcome(report: MagicMock) -> MagicMock:
    outcome = MagicMock()
    outcome.get_result.return_value = report
    return outcome


def _drive_hook(
    plugin: CoredumpPlugin, nodeid: str, report: MagicMock
) -> None:
    """Drive the hookwrapper generator through one cycle."""
    item = MagicMock()
    item.nodeid = nodeid
    gen = plugin.pytest_runtest_makereport(item, MagicMock())
    next(gen)
    outcome = _make_outcome(report)
    try:
        gen.send(outcome)
    except StopIteration:
        pass


class TestCoredumpPluginOnTestFailed:
    def test_calls_collect_for_each_manager(self, tmp_path: "Path") -> None:
        mgr_a = MagicMock()
        mgr_b = MagicMock()
        plugin = CoredumpPlugin({"a": mgr_a, "b": mgr_b})
        plugin._on_test_failed("mod::test_foo", str(tmp_path))
        mgr_a.collect.assert_called_once()
        mgr_b.collect.assert_called_once()

    def test_prefix_derived_from_last_nodeid_segment(
        self, tmp_path: "Path"
    ) -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        plugin._on_test_failed("module::TestClass::test_bar", str(tmp_path))
        _, prefix = mgr.collect.call_args[0]
        assert prefix == "test_bar"

    def test_prefix_sanitizes_special_chars(self, tmp_path: "Path") -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        plugin._on_test_failed("mod::test_foo[param=1]", str(tmp_path))
        _, prefix = mgr.collect.call_args[0]
        assert "[" not in prefix
        assert "]" not in prefix
        assert "=" not in prefix

    def test_repeated_test_name_gets_unique_prefix(
        self, tmp_path: "Path"
    ) -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        plugin._on_test_failed("mod_a::test_open", str(tmp_path))
        plugin._on_test_failed("mod_b::test_open", str(tmp_path))
        plugin._on_test_failed("mod_c::test_open", str(tmp_path))
        prefixes = [c.args[1] for c in mgr.collect.call_args_list]
        assert prefixes == ["test_open", "test_open.2", "test_open.3"]

    def test_distinct_test_names_not_suffixed(self, tmp_path: "Path") -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        plugin._on_test_failed("mod::test_a", str(tmp_path))
        plugin._on_test_failed("mod::test_b", str(tmp_path))
        prefixes = [c.args[1] for c in mgr.collect.call_args_list]
        assert prefixes == ["test_a", "test_b"]

    def test_output_dir_is_product_subdir(self, tmp_path: "Path") -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"myproduct": mgr})
        plugin._on_test_failed("::test_x", str(tmp_path))
        out_dir, _ = mgr.collect.call_args[0]
        assert out_dir == tmp_path / "myproduct"


def _make_product(
    name: str,
    crash: bool = False,
    busyloop: bool = False,
    notalive: bool = False,
) -> MagicMock:
    p = MagicMock()
    p.name = name
    p.crash = crash
    p.busyloop = busyloop
    p.notalive = notalive
    return p


class TestCoredumpPluginTargeting:
    def test_all_products_when_all_healthy(self, tmp_path: "Path") -> None:
        mgr_a = MagicMock()
        mgr_b = MagicMock()
        products = [_make_product("a"), _make_product("b")]
        plugin = CoredumpPlugin({"a": mgr_a, "b": mgr_b}, products)
        plugin._on_test_failed("mod::test_x", str(tmp_path))
        mgr_a.collect.assert_called_once()
        mgr_b.collect.assert_called_once()

    def test_only_unhealthy_product_collected(self, tmp_path: "Path") -> None:
        mgr_a = MagicMock()
        mgr_b = MagicMock()
        products = [_make_product("a", crash=True), _make_product("b")]
        plugin = CoredumpPlugin({"a": mgr_a, "b": mgr_b}, products)
        plugin._on_test_failed("mod::test_x", str(tmp_path))
        mgr_a.collect.assert_called_once()
        mgr_b.collect.assert_not_called()

    def test_unhealthy_product_without_manager_skips_all(
        self, tmp_path: "Path"
    ) -> None:
        mgr_b = MagicMock()
        products = [_make_product("a", notalive=True), _make_product("b")]
        plugin = CoredumpPlugin({"b": mgr_b}, products)
        plugin._on_test_failed("mod::test_x", str(tmp_path))
        mgr_b.collect.assert_not_called()

    def test_all_managers_without_products(self, tmp_path: "Path") -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        plugin._on_test_failed("mod::test_x", str(tmp_path))
        mgr.collect.assert_called_once()


class TestCoredumpPluginHook:
    def test_collects_on_failed_call(self, tmp_path: "Path") -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        pytest.result_dir = str(tmp_path)
        _drive_hook(plugin, "mod::test_x", _make_report(failed=True))
        mgr.collect.assert_called_once()

    def test_skips_on_passed_call(self, tmp_path: "Path") -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        pytest.result_dir = str(tmp_path)
        _drive_hook(plugin, "mod::test_x", _make_report(failed=False))
        mgr.collect.assert_not_called()

    def test_skips_on_setup_phase(self, tmp_path: "Path") -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        pytest.result_dir = str(tmp_path)
        _drive_hook(
            plugin, "mod::test_x", _make_report(when="setup", failed=True)
        )
        mgr.collect.assert_not_called()

    def test_skips_on_teardown_phase(self, tmp_path: "Path") -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        pytest.result_dir = str(tmp_path)
        _drive_hook(
            plugin,
            "mod::test_x",
            _make_report(when="teardown", failed=True),
        )
        mgr.collect.assert_not_called()

    def test_skips_when_result_dir_empty(self) -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        pytest.result_dir = ""
        _drive_hook(plugin, "mod::test_x", _make_report(failed=True))
        mgr.collect.assert_not_called()

    def test_skips_when_result_dir_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mgr = MagicMock()
        plugin = CoredumpPlugin({"p": mgr})
        monkeypatch.delattr(pytest, "result_dir", raising=False)
        _drive_hook(plugin, "mod::test_x", _make_report(failed=True))
        mgr.collect.assert_not_called()
