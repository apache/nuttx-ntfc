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

"""NTFC collector plugin for pytest."""

import os
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import pytest

from ntfc.log.logger import logger
from ntfc.pytest.collecteditem import CollectedItem
from ntfc.testfilter import FilterTest

if TYPE_CHECKING:
    from ntfc.envconfig import EnvConfig

###############################################################################
# Class: CollectorPlugin
###############################################################################


class CollectorPlugin:
    """Custom Pytest collector plugin."""

    def __init__(self, config: "EnvConfig", collectonly: bool = True) -> None:
        """Initialize custom pytest collector plugin."""
        self._config = config
        self._filter = FilterTest(config)

        self._all_items: List[CollectedItem] = []
        self._filtered_items: List[CollectedItem] = []
        self._collectonly = collectonly

        self._skipped_items: List[Tuple[pytest.Item, str]] = []

    def _collected_item(self, item: pytest.Item) -> CollectedItem:
        """Create collected item."""
        path, lineno, name = item.location
        lineno = lineno or 0
        abs_path = os.path.abspath(item.path)
        directory = os.path.dirname(abs_path)
        module = abs_path.replace(pytest.testroot, "")
        root = module.replace(pytest.testroot, "")

        ci = CollectedItem(
            directory,
            module,
            name,
            abs_path,
            lineno,
            item.nodeid,
            pytest.ntfcyaml.get("module", "Unknown_"),
            root,
        )

        return ci

    @property
    def skipped_items(self) -> List[Tuple[pytest.Item, str]]:
        """Get skipped items."""
        return self._skipped_items

    @property
    def filtered(self) -> List[CollectedItem]:
        """Get filtered items."""
        return self._filtered_items

    @property
    def allitems(self) -> List[CollectedItem]:
        """Get all items before filtration."""
        return self._all_items

    def pytest_runtestloop(self, session: pytest.Session) -> bool:
        """Run test loop.

        Do not run tests if we are in collect only mode.
        """
        if session.testsfailed:  # pragma: no cover
            raise session.Interrupted("error during collection")

        # do not run test cases when in collect only mode
        if self._collectonly:
            return True

        loops = self._config.common.get("loops", 1)
        for _ in range(loops):
            if loops > 1:
                print("\n\n" + "=" * 100)
                print("Loop:", _)
                print("=" * 100)

            for i, item in enumerate(session.items):
                nextitem = (
                    session.items[i + 1]
                    if i + 1 < len(session.items)
                    else None
                )

                logger.debug(f"run test:{item}")

                item.config.hook.pytest_runtest_protocol(
                    item=item, nextitem=nextitem
                )
                if session.shouldfail:  # pragma: no cover
                    raise session.Failed(session.shouldfail)
                if session.shouldstop:  # pragma: no cover
                    raise session.Interrupted(session.shouldstop)

        return True

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        """Pytest collection finish callback."""

    def _filter_modules(
        self,
        ci: CollectedItem,
        include: List[str],
        exclude: List[str],
        exclude_test: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """Filter modules based on include/exclude lists.

        :param ci: Collected item to check.
        :param include: Modules to run; everything else is skipped.
        :param exclude: Modules to skip.
        :param exclude_test: Test names to skip, e.g.
            ``test_ltp_integration[ltp_interfaces_pthread_rwlock_unlock_4_2]``.
        :return: ``(skip, reason)`` tuple.
        """
        if include and ci.module2 not in include:
            return True, "not in include_module"

        if exclude and ci.module2 in exclude:
            return True, "excluded module"

        if exclude_test and ci.name in exclude_test:
            return True, "excluded test"

        return False, ""

    def _order_items(
        self, items: List[pytest.Item], order_map: Dict[str, int]
    ) -> List[pytest.Item]:
        """Order test items based on the order map."""

        def sort_key(test_item: pytest.Item) -> Tuple[int, int]:
            v = order_map.get(test_item._collected.module2)
            if v is None:
                return (1, 0)
            if v > 0:
                return (0, v)
            # v < 0
            return (2, v)

        return sorted(items, key=sort_key)

    def pytest_collection_modifyitems(
        self,
        config: pytest.Config,
        items: list[pytest.Item],  # pylint: disable=unused-argument
    ) -> None:
        """Modify the `items` list after collection is completed.

        :param config:
        :param items:
        """
        tmp: List[pytest.Item] = []

        module = pytest.cfgtest.get("module", {})
        include_module = module.get("include_module", [])
        exclude_module = module.get("exclude_module", [])
        exclude_test = module.get("exclude_test", [])
        order_list = module.get("order", [])
        order_map = {
            e["module"]: int(e["value"])
            for e in order_list
            if e.get("module") and e.get("value") is not None
        }

        for item in items:
            ci = self._collected_item(item)
            item._collected = ci
            self._all_items.append(ci)

            skip, reason = self._filter.check_test_support(item)
            if not skip:
                skip, reason = self._filter_modules(
                    ci, include_module, exclude_module, exclude_test
                )

            if skip:
                skip_reason = reason or "unknown reason"
                self._skipped_items.append((item, skip_reason))
                item.add_marker(pytest.mark.skip(reason=skip_reason))
                continue

            self._filtered_items.append(ci)
            tmp.append(item)

        if order_map:
            tmp = self._order_items(tmp, order_map)

        # Update filtered items list to match new order
        self._filtered_items = [item._collected for item in tmp]

        # overwrite items
        items[:] = tmp
