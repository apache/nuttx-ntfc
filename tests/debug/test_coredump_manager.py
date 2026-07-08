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

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from ntfc.debug.config import CoredumpConfig
from ntfc.debug.coredump.base import CoredumpHandler
from ntfc.debug.coredump.manager import CoredumpManager


def _make_cfg(
    enable: bool = True,
    limit: int = 5,
    collection_type: str = "auto",
) -> CoredumpConfig:
    raw: dict = {
        "enable": enable,
        "limit": limit,
        "type": collection_type,
    }
    return CoredumpConfig(raw)


def _mock_handler(
    name: str = "mock",
    priority: int = 10,
    available: bool = True,
    collect_result: bool = True,
) -> CoredumpHandler:
    handler = MagicMock(spec=CoredumpHandler)
    handler.name = name
    handler.priority = priority
    handler.is_available.return_value = available
    handler.collect.return_value = collect_result
    handler.is_enabled.return_value = True
    return handler


class TestCoredumpManagerDisabled:
    def test_collect_returns_false_when_disabled(self, tmp_path: "Path"):
        cfg = _make_cfg(enable=False)
        mgr = CoredumpManager(cfg)
        h = _mock_handler()
        mgr.register(h)
        assert mgr.collect(tmp_path, "test") is False

    def test_count_not_incremented_when_disabled(self, tmp_path: "Path"):
        cfg = _make_cfg(enable=False)
        mgr = CoredumpManager(cfg)
        mgr.collect(tmp_path, "test")
        assert mgr.collected_count == 0


class TestCoredumpManagerLimit:
    def test_collect_returns_false_when_limit_reached(self, tmp_path: "Path"):
        cfg = _make_cfg(enable=True, limit=2)
        mgr = CoredumpManager(cfg)
        h = _mock_handler(collect_result=True)
        mgr.register(h)

        assert mgr.collect(tmp_path, "a") is True
        assert mgr.collect(tmp_path, "b") is True
        assert mgr.collect(tmp_path, "c") is False

    def test_count_equals_limit_when_limit_reached(self, tmp_path: "Path"):
        cfg = _make_cfg(enable=True, limit=1)
        mgr = CoredumpManager(cfg)
        h = _mock_handler(collect_result=True)
        mgr.register(h)
        mgr.collect(tmp_path, "x")
        assert mgr.collected_count == 1


class TestCoredumpManagerFallback:
    def test_falls_back_to_next_handler_on_failure(self, tmp_path: "Path"):
        cfg = _make_cfg()
        mgr = CoredumpManager(cfg)
        primary = _mock_handler(name="gdb", priority=10, collect_result=False)
        fallback = _mock_handler(
            name="fastboot", priority=20, collect_result=True
        )
        mgr.register(primary)
        mgr.register(fallback)

        assert mgr.collect(tmp_path, "test") is True
        primary.collect.assert_called_once()
        fallback.collect.assert_called_once()
        assert mgr.collected_count == 1

    def test_returns_false_when_all_handlers_fail(self, tmp_path: "Path"):
        cfg = _make_cfg()
        mgr = CoredumpManager(cfg)
        a = _mock_handler(name="gdb", priority=10, collect_result=False)
        b = _mock_handler(name="fastboot", priority=20, collect_result=False)
        mgr.register(a)
        mgr.register(b)

        assert mgr.collect(tmp_path, "test") is False
        a.collect.assert_called_once()
        b.collect.assert_called_once()
        assert mgr.collected_count == 0


class TestCoredumpManagerPrioritySelection:
    def test_selects_lower_priority_first(self, tmp_path: "Path"):
        cfg = _make_cfg()
        mgr = CoredumpManager(cfg)
        h_low = _mock_handler(name="alpha", priority=5, collect_result=True)
        h_high = _mock_handler(name="beta", priority=20, collect_result=True)
        mgr.register(h_high)
        mgr.register(h_low)
        result = mgr.collect(tmp_path, "t")
        assert result is True
        h_low.collect.assert_called_once()
        h_high.collect.assert_not_called()

    def test_skips_unavailable_handler(self, tmp_path: "Path"):
        cfg = _make_cfg()
        mgr = CoredumpManager(cfg)
        unavail = _mock_handler(name="unavail", priority=1, available=False)
        avail = _mock_handler(
            name="avail", priority=10, available=True, collect_result=True
        )
        mgr.register(unavail)
        mgr.register(avail)
        result = mgr.collect(tmp_path, "t")
        assert result is True
        avail.collect.assert_called_once()
        unavail.collect.assert_not_called()


class TestCoredumpManagerNameSelection:
    def test_selects_by_name_when_not_auto(self, tmp_path: "Path"):
        cfg = _make_cfg(collection_type="gdb")
        mgr = CoredumpManager(cfg)
        gdb_h = _mock_handler(name="gdb", priority=10, collect_result=True)
        other_h = _mock_handler(
            name="fastboot", priority=5, collect_result=True
        )
        mgr.register(gdb_h)
        mgr.register(other_h)
        result = mgr.collect(tmp_path, "t")
        assert result is True
        gdb_h.collect.assert_called_once()
        other_h.collect.assert_not_called()

    def test_returns_false_when_named_handler_not_registered(
        self, tmp_path: "Path"
    ):
        cfg = _make_cfg(collection_type="ymodem")
        mgr = CoredumpManager(cfg)
        h = _mock_handler(name="gdb", collect_result=True)
        mgr.register(h)
        assert mgr.collect(tmp_path, "t") is False


class TestCoredumpManagerNoHandler:
    def test_returns_false_when_no_handler_registered(self, tmp_path: "Path"):
        cfg = _make_cfg()
        mgr = CoredumpManager(cfg)
        assert mgr.collect(tmp_path, "t") is False

    def test_returns_false_when_all_handlers_unavailable(
        self, tmp_path: "Path"
    ):
        cfg = _make_cfg()
        mgr = CoredumpManager(cfg)
        h = _mock_handler(available=False)
        mgr.register(h)
        assert mgr.collect(tmp_path, "t") is False


class TestCoredumpManagerCount:
    def test_count_incremented_only_on_success(self, tmp_path: "Path"):
        cfg = _make_cfg()
        mgr = CoredumpManager(cfg)
        success_h = _mock_handler(
            name="good", priority=10, collect_result=True
        )
        fail_h = _mock_handler(name="bad", priority=20, collect_result=False)
        mgr.register(success_h)
        mgr.collect(tmp_path, "s")
        assert mgr.collected_count == 1

        mgr2 = CoredumpManager(cfg)
        mgr2.register(fail_h)
        mgr2.collect(tmp_path, "f")
        assert mgr2.collected_count == 0

    def test_reset_clears_count(self, tmp_path: "Path"):
        cfg = _make_cfg()
        mgr = CoredumpManager(cfg)
        h = _mock_handler(collect_result=True)
        mgr.register(h)
        mgr.collect(tmp_path, "a")
        mgr.collect(tmp_path, "b")
        assert mgr.collected_count == 2
        mgr.reset()
        assert mgr.collected_count == 0


class TestCoredumpManagerRegister:
    def test_register_multiple_handlers(self, tmp_path: "Path"):
        cfg = _make_cfg()
        mgr = CoredumpManager(cfg)
        handlers = [
            _mock_handler(name="h1", priority=30, collect_result=False),
            _mock_handler(name="h2", priority=20, collect_result=False),
            _mock_handler(name="h3", priority=10, collect_result=True),
        ]
        for h in handlers:
            mgr.register(h)
        result = mgr.collect(tmp_path, "t")
        assert result is True
        handlers[2].collect.assert_called_once()

    def test_disabled_handler_skipped(self, tmp_path: "Path"):
        cfg = _make_cfg()
        mgr = CoredumpManager(cfg)
        h = MagicMock(spec=CoredumpHandler)
        h.name = "mock"
        h.priority = 5
        h.is_available.return_value = True
        h.collect.return_value = True
        h.is_enabled.return_value = False
        mgr.register(h)
        assert mgr.collect(tmp_path, "t") is False

    @pytest.mark.parametrize("limit", [0, 1, 10])
    def test_limit_zero_always_returns_false(
        self, tmp_path: "Path", limit: int
    ):
        cfg = _make_cfg(limit=limit)
        mgr = CoredumpManager(cfg)
        h = _mock_handler(collect_result=True)
        mgr.register(h)
        for _ in range(limit):
            mgr.collect(tmp_path, "fill")
        # now at limit
        assert mgr.collect(tmp_path, "over") is False
