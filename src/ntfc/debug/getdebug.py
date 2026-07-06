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

"""Factory creating debug plugins from product configuration."""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from ntfc.debug.coredump.fastboot_handler import FastbootHandler
from ntfc.debug.coredump.gdb_handler import GdbHandler
from ntfc.debug.coredump.local_file_handler import LocalFileHandler
from ntfc.debug.coredump.manager import CoredumpManager
from ntfc.debug.coredump.syslog_handler import SyslogHandler
from ntfc.debug.coredump.ymodem_handler import YmodemHandler
from ntfc.debug.gdb.controller import GdbController
from ntfc.lib.fastboot.controller import FastbootController
from ntfc.lib.ymodem.controller import YmodemController
from ntfc.log.logger import logger
from ntfc.pytest.coredump_plugin import CoredumpPlugin

if TYPE_CHECKING:
    from ntfc.debug.config import DebugConfig
    from ntfc.product import Product

###############################################################################
# Class: DebugSetup
###############################################################################


class DebugSetup:
    """Owns debug plugins and controller lifecycles for one test session.

    :param plugins: Pytest plugin instances to pass to the test run.
    :param controllers_by_product: GDB controllers that must be opened
        before the run and closed afterwards, keyed by product name so
        a rebooted product's controller(s) can be re-attached.
    """

    def __init__(
        self,
        plugins: List[Any],
        controllers_by_product: Dict[str, List[GdbController]],
    ) -> None:
        """Initialize :class:`DebugSetup`.

        :param plugins: Pytest plugin instances.
        :param controllers_by_product: GDB controllers managed by this
            setup, keyed by the product name they belong to.
        """
        self._plugins = plugins
        self._controllers_by_product = controllers_by_product
        self._started: List[GdbController] = []
        self._result_dir = ""

    @property
    def plugins(self) -> List[Any]:
        """Return the pytest plugin instances for the test run."""
        return list(self._plugins)

    def _start_one(self, product_name: str, ctrl: GdbController) -> None:
        """Start and set up a single controller, tracking it if it opens.

        Each product gets its own subdirectory of the session result
        directory so two products' in-GDB auto-generated coredumps
        (written directly by GDB, with only 1-second timestamp
        resolution) can never collide on the same path.

        :param product_name: Name of the product the controller serves.
        :param ctrl: Controller to start.
        """
        if not ctrl.start():
            logger.warning("debug: failed to start GDB controller")
            return
        ctrl.setup(f"{self._result_dir}/{product_name}")
        self._started.append(ctrl)

    def start(self, result_dir: str) -> None:
        """Start all GDB controllers and send their setup commands.

        A controller that fails to start is logged and skipped so the
        test session can continue without GDB support.  No-ops when
        *result_dir* is empty (log collection disabled).

        :param result_dir: Session result directory used for coredumps.
        """
        if not result_dir:
            return

        self._result_dir = result_dir
        for name, controllers in self._controllers_by_product.items():
            for ctrl in controllers:
                self._start_one(name, ctrl)

    def stop(self) -> None:
        """Stop all controllers that were successfully started."""
        for ctrl in self._started:
            ctrl.stop()
        self._started.clear()

    def restart_controllers(self, product_name: str) -> None:
        """Re-attach the GDB controller(s) of one rebooted product.

        A device reboot spawns a new process (or, for real hardware,
        resets the target in place), so any GDB session already
        attached to it is stale: it keeps polling as "running" while
        talking to a process/target that is gone, silently breaking
        coredump collection for the rest of the session.

        :param product_name: Name of the product whose device rebooted.
        """
        if not self._result_dir:
            return

        for ctrl in self._controllers_by_product.get(product_name, []):
            if ctrl in self._started:
                ctrl.stop()
                self._started.remove(ctrl)
            self._start_one(product_name, ctrl)

    def restart_all_controllers(self) -> None:
        """Re-attach every product's GDB controller(s).

        Called after ntfc's built-in crash recovery
        (:meth:`~ntfc.pytest.configure.PytestConfigPlugin._device_reboot`)
        reboots the session's products, since that reboot restarts
        every product unconditionally and so invalidates every GDB
        session attached to them.
        """
        for product_name in self._controllers_by_product:
            self.restart_controllers(product_name)


###############################################################################
# Public functions
###############################################################################


def _gdb_handler_register(
    mgr: CoredumpManager,
    product: "Product",
    controllers: List[GdbController],
) -> None:
    """Register a GDB coredump handler when prerequisites are met.

    Requires a core 0 ``elf_path`` plus either a ``gdb.target`` to
    attach to or ``gdb.attach`` (simulator PID attach); otherwise a
    warning is logged and no handler is registered.

    :param mgr: Coredump manager of the product.
    :param product: Product being configured.
    :param controllers: List collecting created GDB controllers.
    """
    cfg = product.conf.debug
    elf_path = product.conf.cfg_core(0).elf_path

    if not elf_path or not (cfg.gdb.target or cfg.gdb.attach):
        logger.warning(
            f"debug: product {product.name} has gdb enabled "
            f"but coredump collection requires elf_path and "
            f"either gdb.target or gdb.attach"
        )
        return

    device = product.core(0).device
    ctrl = GdbController(
        Path(elf_path), cfg.gdb, pid_provider=lambda: device.pid
    )
    panic = product.force_panic if cfg.gdb.force_panic else None
    mgr.register(
        GdbHandler(
            ctrl,
            force_panic=panic,
            crash_check=lambda: bool(product.crash),
            auto_dump=cfg.gdb.auto_breakpoints,
        )
    )
    controllers.append(ctrl)


def _register_coredump_handlers(
    mgr: CoredumpManager,
    product: "Product",
    cfg: "DebugConfig",
    controllers: List[GdbController],
) -> None:
    """Register the coredump handlers configured for one product.

    :param mgr: Coredump manager of the product.
    :param product: Product being configured.
    :param cfg: Debug configuration of the product.
    :param controllers: List collecting created GDB controllers.
    """
    if cfg.gdb.enable:
        _gdb_handler_register(mgr, product, controllers)

    if cfg.fastboot.dev_sn:
        fastboot = FastbootController(cfg.fastboot.dev_sn)
        mgr.register(
            FastbootHandler(
                fastboot, cfg.fastboot.mem_addr, cfg.fastboot.mem_size
            )
        )

    if cfg.ymodem.serial_port and cfg.ymodem.sbrb_path:
        ymodem = YmodemController(
            cfg.ymodem.serial_port,
            Path(cfg.ymodem.sbrb_path),
            cfg.ymodem.baud_rate,
        )
        mgr.register(YmodemHandler(ymodem, product.core(0).device))

    if cfg.local_file.core_dir:
        mgr.register(LocalFileHandler(cfg.local_file))

    if cfg.syslog.enable:
        mgr.register(SyslogHandler(product.core(0).device))


def get_debug_setup(products: "List[Product]") -> DebugSetup:
    """Create debug plugins and controllers from product configuration.

    For every product with ``debug.coredump.enable`` set a
    :class:`~ntfc.debug.coredump.manager.CoredumpManager` is created and
    the handlers configured in the product ``debug`` section (GDB,
    fastboot, Ymodem, local file, syslog) are registered.  A single
    :class:`~ntfc.pytest.coredump_plugin.CoredumpPlugin` serves all
    managers.

    Rebooting an unhealthy device between tests is core ntfc behavior
    (:meth:`~ntfc.pytest.configure.PytestConfigPlugin._device_reboot`),
    not part of this debug feature set.

    :param products: Products created for the test session.
    :return: :class:`DebugSetup` with the plugins and controllers.
    """
    managers: Dict[str, CoredumpManager] = {}
    controllers_by_product: Dict[str, List[GdbController]] = {}
    plugins: List[Any] = []

    for product in products:
        cfg = product.conf.debug

        if not cfg.coredump.enable:
            continue

        if product.conf.cores_num > 1:
            logger.warning(
                f"debug: product {product.name} has multiple cores; "
                f"coredump collection only supports core 0"
            )

        mgr = CoredumpManager(cfg.coredump)
        controllers: List[GdbController] = []
        _register_coredump_handlers(mgr, product, cfg, controllers)
        controllers_by_product[product.name] = controllers

        managers[product.name] = mgr
        logger.info(f"debug: coredump collection enabled for {product.name}")

    debug_setup = DebugSetup(plugins, controllers_by_product)

    if managers:
        plugins.append(CoredumpPlugin(managers, products))

    return debug_setup
