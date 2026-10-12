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

"""Pytest plugin providing the ``resources`` leak detection fixture."""

from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional

import pytest

from ntfc.log.logger import logger
from ntfc.resmon.base import clean_output
from ntfc.resmon.monitor import ResourceMonitor, Sampler
from ntfc.resmon.probes import PROBES, make_probes

if TYPE_CHECKING:
    from ntfc.core import ProductCore
    from ntfc.envconfig import EnvConfig
    from ntfc.product import Product

###############################################################################
# Class: ResourcePlugin
###############################################################################


class ResourcePlugin:
    """Sample target resources around tests that request ``resources``.

    The fixture records a baseline before the test body, re-samples after
    it and raises :class:`~ntfc.resmon.monitor.ResourceLeakError` when a
    probe reports a delta that does not settle. Probes whose Kconfig
    gates fail on any product are dropped with a warning.

    :param config: Environment configuration.
    :param products: Products under test.
    """

    COMMAND_TIMEOUT = 10

    def __init__(self, config: "EnvConfig", products: "List[Product]"):
        """Initialize the plugin."""
        self._cfg = config.resources
        self._products = products
        self._cores: "Dict[str, ProductCore]" = {}

    def _options(self, marker: Optional[Any]) -> Dict[str, Any]:
        """Merge the ``resources`` marker kwargs over the configuration."""
        return {**self._cfg, **(marker.kwargs if marker else {})}

    @staticmethod
    def _gate_failures(product: "Product", name: str) -> List[str]:
        """Return the Kconfig gates of a probe that fail on a product."""
        conf = product.conf
        core = conf.primary_test_core_index
        return [
            symbol
            for symbol, expected in PROBES[name].kconfig
            if bool(conf.kv_check(symbol, core)) != expected
        ]

    def probe_names(self, marker: Optional[Any]) -> List[str]:
        """Return the probes available on every product.

        :param marker: ``resources`` marker of the test, if any.
        :raises ValueError: Unknown probe name.
        """
        names = []
        for name in self._options(marker)["probes"]:
            if name not in PROBES:
                raise ValueError(f"unknown resource probe: {name}")
            failures = {
                product.name: self._gate_failures(product, name)
                for product in self._products
            }
            failed = {p: f for p, f in failures.items() if f}
            if failed:
                logger.warning(
                    f"resources: probe '{name}' unavailable: {failed}"
                )
                continue
            names.append(name)
        return names

    def _sampler(self, core: "ProductCore") -> Sampler:
        """Return a callable that runs one command on a core."""

        def send(cmd: str) -> str:
            ret = core.sendCommandReadUntilPattern(
                cmd, timeout=self.COMMAND_TIMEOUT
            )
            return clean_output(ret.output, cmd, core.prompt.decode())

        return send

    def targets(self) -> Dict[str, Sampler]:
        """Return the cores to sample, keyed by ``product/core``."""
        targets = {}
        for product in self._products:
            conf = product.conf
            indices = (
                [conf.primary_test_core_index]
                if conf.is_smp
                else conf.active_core_indices
            )
            for idx in indices:
                core = product.core(idx)
                name = f"{product.name}/{core.name}"
                self._cores[name] = core
                targets[name] = self._sampler(core)
        return targets

    def monitor(self, marker: Optional[Any]) -> ResourceMonitor:
        """Build the monitor for one test.

        :param marker: ``resources`` marker of the test, if any.
        """
        options = self._options(marker)
        if not options["enabled"]:
            return ResourceMonitor([], {})

        missing = [
            product.name
            for product in self._products
            if not product.conf.kv_check(
                "CONFIG_FS_PROCFS", product.conf.primary_test_core_index
            )
        ]
        if missing:
            logger.warning(
                f"resources: CONFIG_FS_PROCFS not set on {missing}, "
                "resource monitoring disabled"
            )
            return ResourceMonitor([], {})

        return ResourceMonitor(
            make_probes(self.probe_names(marker), options),
            self.targets(),
            settle_retries=int(options["settle_retries"]),
            settle_delay=float(options["settle_delay"]),
        )

    def _unhealthy(self) -> bool:
        """Return True when any product is in a fault state."""
        return any(
            p.crash or p.busyloop or p.flood or p.notalive
            for p in self._products
        )

    def _record(self, request: Any, monitor: ResourceMonitor) -> None:
        """Attach the final delta to the report and the device logs."""
        diff = monitor.last_diff
        request.node.user_properties.append(("resources", diff))
        for target, probes in diff.items():
            for probe, lines in probes.items():
                for line in lines:
                    self._cores[target].device.log_event(
                        f"resources {probe}: {line}"
                    )

    @pytest.fixture  # type: ignore
    def resources(self, request: Any) -> Iterator[ResourceMonitor]:
        """Check that the test releases the resources it used.

        Request this fixture to sample the configured probes before the
        test body and again after it. A remaining delta fails the test at
        teardown. Use ``@pytest.mark.resources(probes=[...], ...)`` to
        override the configuration for one test. List it after
        ``switch_to_core`` so sampling happens on the switched core.

        :yield: :class:`~ntfc.resmon.monitor.ResourceMonitor`
        """
        monitor = self.monitor(request.node.get_closest_marker("resources"))
        monitor.baseline()

        yield monitor

        if not monitor.active:
            return
        if self._unhealthy():
            logger.warning("resources: product unhealthy, skipping check")
            return
        try:
            monitor.check()
        finally:
            self._record(request, monitor)
