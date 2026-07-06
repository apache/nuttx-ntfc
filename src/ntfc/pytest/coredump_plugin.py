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

"""Pytest plugin that triggers coredump collection on test failures."""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pytest
from pluggy import HookimplMarker

from ntfc.log.logger import logger

if TYPE_CHECKING:
    from ntfc.debug.coredump.manager import CoredumpManager
    from ntfc.product import Product

hookimpl = HookimplMarker("pytest")


class CoredumpPlugin:
    """Collect coredumps from all registered products on test failures.

    Each product maps to a :class:`~ntfc.debug.coredump.manager\
.CoredumpManager`.  When a test body fails the plugin calls
    :meth:`~ntfc.debug.coredump.manager.CoredumpManager.collect` for
    every product, writing output into a per-product subdirectory of
    ``pytest.result_dir``.

    When product instances are provided and at least one of them is in
    an abnormal state (crashed, busy-looping, or dead), collection is
    restricted to those products so healthy devices are not stalled and
    their per-session limits are not consumed by unrelated failures.

    :param managers: Mapping of product name to its
        :class:`~ntfc.debug.coredump.manager.CoredumpManager`.
    :param products: Products used for health-based targeting.
    """

    def __init__(
        self,
        managers: "Dict[str, CoredumpManager]",
        products: "Optional[List[Product]]" = None,
    ) -> None:
        """Initialize :class:`CoredumpPlugin`.

        :param managers: Mapping of product name to manager.
        :param products: Products used for health-based targeting.
        """
        self._managers = managers
        self._products = products or []
        self._prefix_counts: Dict[str, int] = {}

    def _target_managers(self) -> "Dict[str, CoredumpManager]":
        """Return the managers to collect from for the current failure.

        :return: Managers of unhealthy products when any product is
            unhealthy, all managers otherwise.
        """
        unhealthy = {
            p.name
            for p in self._products
            if p.crash or p.busyloop or p.notalive
        }
        if not unhealthy:
            return self._managers

        return {
            name: mgr
            for name, mgr in self._managers.items()
            if name in unhealthy
        }

    def _unique_prefix(self, nodeid: str) -> str:
        """Derive a session-unique filename prefix from a test node ID.

        Tests in different files or classes can share their terminal
        name (and reruns repeat it), so repeated prefixes get a numeric
        suffix to avoid overwriting earlier coredumps.

        :param nodeid: Pytest node ID of the failed test.
        :return: Sanitized, session-unique prefix.
        """
        base = re.sub(r"[^\w.-]", "_", nodeid.split("::")[-1])
        count = self._prefix_counts.get(base, 0)
        self._prefix_counts[base] = count + 1
        return base if count == 0 else f"{base}.{count + 1}"

    def _on_test_failed(self, nodeid: str, result_dir: str) -> None:
        """Trigger coredump collection for all products.

        :param nodeid: Pytest node ID of the failed test.
        :param result_dir: Session result directory path.
        """
        prefix = self._unique_prefix(nodeid)
        out = Path(result_dir)
        for name, mgr in self._target_managers().items():
            logger.debug(
                f"coredump: collecting for product {name} prefix {prefix}"
            )
            mgr.collect(out / name, prefix)

    @hookimpl(hookwrapper=True, trylast=True)
    def pytest_runtest_makereport(self, item: Any, call: Any) -> Any:
        """Collect coredump when a test call phase fails.

        :param item: The pytest test item.
        :param call: The call info for the phase.
        :yield: None
        """
        del call
        outcome = yield
        report = outcome.get_result()
        if report.when != "call" or not report.failed:
            return
        result_dir = getattr(pytest, "result_dir", "")
        if not result_dir:
            return
        self._on_test_failed(item.nodeid, result_dir)
