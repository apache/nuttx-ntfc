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

"""NTFC plugin for pytest."""

import importlib.util
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import pytest
import yaml  # type: ignore
from pluggy import HookimplMarker

from ntfc.envconfig import EnvConfig
from ntfc.log.logger import logger
from ntfc.log.manager import LogManager
from ntfc.product import Product
from ntfc.products import ProductsHandler

from .collected import Collected
from .collector import CollectorPlugin
from .configure import PytestConfigPlugin
from .gtest_plugin import GtestParserPlugin
from .parsers import ParserPlugin
from .runner import RunnerPlugin
from .signal_plugin import SignalPlugin

# required for plugin
hookimpl = HookimplMarker("pytest")


###############################################################################
# Class: MyPytest
###############################################################################


class MyPytest:
    """Custom wrapper for pytest."""

    NTFC_YAML_FILE = "ntfc.yaml"
    SESSION_CONFIG_FILE = "session.config.txt"

    def __init__(
        self,
        config: Dict[str, Any],
        exit_on_fail: bool = False,
        verbose: bool = False,
        confjson: Optional[Dict[str, Any]] = None,
        modules: Optional[List[str]] = None,
    ) -> None:
        """Initialize pytest wrapper.

        :param config: configuration instance
        :param exit_on_fail: exit on first test fail if set to True
        :param verbose: verbose output if set to True
        :param confjson: test session configuration
        :param modules: module filetr
        """
        self._config = EnvConfig(config)
        self._opt: List[str] = []
        self._plugins: List[Any] = []
        self._cfg_module: Dict[str, Any] = {}
        self.result_dir: str = ""
        self._cfg_test: Dict[str, Any] = {}

        if exit_on_fail:
            self._opt.append("-x")

        if verbose:
            self._opt.append("-qq")

        # test module config
        if confjson:
            self._cfg_test = confjson
        else:
            self._cfg_test = {}

        # Overwrite module filter if specified
        if modules:
            if "module" not in self._cfg_test:  # pragma: no cover
                self._cfg_test["module"] = {}
            self._cfg_test["module"]["include_module"] = modules
            logger.info(f"Running tests from modules: {modules}")

        pytest.cfgtest = self._cfg_test

        # configure plugin
        hookimpl_marker = hookimpl(hookwrapper=True)
        hookimpl_marker(
            PytestConfigPlugin.__dict__["pytest_runtest_makereport"]
        )
        self._ptconfig = PytestConfigPlugin(self._config, verbose)

        # add our custom pytest plugin
        self._plugins.append(self._ptconfig)
        self._plugins.append(SignalPlugin())
        self._plugins.append(ParserPlugin())
        self._plugins.append(GtestParserPlugin())

    def _write_session_config(self, result_dir: str) -> None:
        """Write resolved session configuration into result directory."""
        path = os.path.join(result_dir, self.SESSION_CONFIG_FILE)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._config.config, f, indent=2, sort_keys=True)
            f.write("\n")

    def _kv_validate(
        self, product: Product, core: int
    ) -> Tuple[bool, Optional[Any]]:  # pragma: no cover
        """Check if configuration can be used with this tool."""
        requirements = pytest.ntfcyaml.get("requirements", {})

        for req in requirements:
            if product.conf.kv_check(req[0], core) != req[1]:
                return False, req
        return True, None

    def _create_products(self, config: "EnvConfig") -> List[Product]:
        """Create products according to configuration."""
        tmp = []
        for prod_config in config.product:
            p = Product(prod_config)

            # check config requirements
            for core in range(len(p.conf.cores)):
                ret = self._kv_validate(p, core)
                if ret[0] is False:  # pragma: no cover
                    raise IOError(f"Missing kconfig dependency: {ret[1]}")

            tmp.append(p)

        return tmp

    def _run(self, extra_opt: List[str], extra_plugins: List[Any]) -> Any:
        """Run pytest.

        :param extra_opt:
        :param extra_plugins:
        """
        # get default options and plugins
        opt = self._opt[:]
        plugins = self._plugins[:]

        # extra options and plugins
        opt.extend(extra_opt)
        plugins.extend(extra_plugins)

        # disable pytest stdout capture so we can use print() when pytest
        # is running
        opt.append("-s")

        # override tox.ini configuration from package root
        opt.extend(["--color=yes", "--override-ini", "addopts="])

        # don't generate __pycache__ for test cases
        # this can break modules logic when we change testpath
        # between ntfc runs.
        # REVISIT: not sure what is the impact on perfomances of this
        sys.dont_write_bytecode = True

        # run pytest in collection-only mode with our custom plugin
        return pytest.main(opt, plugins=plugins)

    def _find_config_file(self, testpath: str) -> Optional[str]:
        """Search for ntfc.yaml in testpath and parent directories.

        :param testpath: starting path for search
        :return: path to ntfc.yaml if found, None otherwise
        """
        current_path = os.path.abspath(testpath)

        # search upwards from testpath
        while True:
            config_file = os.path.join(current_path, self.NTFC_YAML_FILE)
            if os.path.exists(config_file):
                return str(config_file)

            parent = os.path.dirname(current_path)
            if parent == current_path:  # reached root
                break
            current_path = parent

        return None

    def _module_config(self, path: Optional[str]) -> None:
        """Load test module configuration."""
        self._cfg_module = {}
        if path is None:
            logger.info(f"no {self.NTFC_YAML_FILE} file found")
            return

        try:
            logger.info(f"{self.NTFC_YAML_FILE} file {path}")

            with open(path, encoding="utf-8") as f:  # pragma: no cover
                self._cfg_module = yaml.safe_load(f)

        except TypeError:  # pragma: no cover
            pass

    def _init_pytest(self, testpath: str) -> None:
        """Initialize pytest environment."""
        # inject some objects into pytest module
        # load per test module configuration
        conf_path = self._find_config_file(testpath)
        self._module_config(conf_path)

        # store some objects for later use in pytest context
        pytest.ntfcyaml = self._cfg_module
        pytest.products = self._create_products(self._config)
        pytest.product = ProductsHandler(pytest.products)
        pytest.task = self._config.product_get(product=0)
        pytest.testpath = os.path.abspath(testpath)

        if conf_path:
            pytest.testroot = conf_path.replace(self.NTFC_YAML_FILE, "")
        else:
            pytest.testroot = testpath

        # python dependencies for test cases module
        dependencies = self._cfg_module.get("dependencies", [])
        for dep in dependencies:
            if importlib.util.find_spec(dep) is None:  # pragma: no cover
                raise ImportError(
                    f"Python package from module"
                    f" dependencies not found {dep}"
                )

    def _device_stop(self) -> None:
        """Stop all devices that were started for testing."""
        if not hasattr(pytest, "products"):
            return  # pragma: no cover

        for product in pytest.products:
            for core_idx in range(len(product.cores)):
                core = product.core(core_idx)
                try:
                    core._device.stop()
                except Exception:  # pragma: no cover
                    logger.warning(
                        "Failed to stop device %s core %d",
                        product.name,
                        core_idx,
                    )

    def _device_start(self) -> None:
        """Start device to test."""
        for product in pytest.products:
            if not product.core(0).device.notalive:
                logger.info(
                    "device %s already alive, skip start",
                    product.name,
                )
                continue

            # start device
            product.start()
            # finish product initialization
            product.init()

        # Enable heartbeat monitoring for all devices after startup
        # Read heartbeat configuration
        heartbeat_cfg = self._config.heartbeat
        if heartbeat_cfg["enabled"]:  # pragma: no cover
            logger.info(
                f"Heartbeat monitoring enabled: "
                f"interval={heartbeat_cfg['interval']}s, "
                f"threshold={heartbeat_cfg['threshold']}"
            )
            for product in pytest.products:
                for core_idx in range(len(product.cores)):
                    core = product.core(core_idx)
                    # Access device through ProductCore
                    device = core._device
                    logger.info(
                        f"Enabling heartbeat monitoring for "
                        f"{product.name} core {core_idx}"
                    )
                    device._state_mgr.enable_heartbeat(
                        interval=float(heartbeat_cfg["interval"]),
                        threshold=int(heartbeat_cfg["threshold"]),
                    )
        else:
            logger.info("Heartbeat monitoring disabled (via config)")

    def runner(
        self,
        testpath: str,
        result: Dict[str, Any],
        nologs: bool = False,
        selected_tests: Optional[List[str]] = None,
        reinit: bool = True,
    ) -> Any:
        """Run tests.

        :param testpath: path to test directory
        :param result: result output configuration
        :param nologs: disable log collection
        :param selected_tests: list of test node IDs to run
        :param reinit: re-initialize pytest environment (default: True)
        """
        # initialize pytest env
        if reinit:
            self._init_pytest(testpath)

        opt = []

        # configure timeouts
        timeout = self._config.common.get("timeout", 800)
        timeout_session = self._config.common.get("timeout_session", 3600)
        opt.append("--timeout=" + str(timeout))
        opt.append("--session-timeout=" + str(timeout_session))

        # Filter to selected tests if specified
        if selected_tests:  # pragma: no cover
            for nodeid in selected_tests:
                opt.append(nodeid)
        else:
            opt.append(testpath)

        if not nologs:  # pragma: no cover
            if "result_dir" in result:
                # Use pre-created result directory (multi-session mode)
                pytest.result_dir = result["result_dir"]
                os.makedirs(pytest.result_dir, exist_ok=True)
            else:
                # create result directory via LogManager
                log_manager = LogManager(result.get("logcfg"))
                log_manager.cleanup()
                pytest.result_dir = log_manager.new_session_dir()
            self.result_dir = pytest.result_dir
            self._write_session_config(pytest.result_dir)

            # always include HTML and XML report if logs enabled
            path = os.path.join(pytest.result_dir, "report.html")
            opt.append(f"--html={path}")
            path = os.path.join(pytest.result_dir, "report.xml")
            opt.append(f"--junitxml={path}")

            # additional reports
            if result.get("json"):
                path = os.path.join(pytest.result_dir, "report.json")
                opt.append(f"--json={path}")
        else:
            pytest.result_dir = ""

        # collector plugin
        collector = CollectorPlugin(self._config, False)

        # run pytest with our custom test plugin
        runner = RunnerPlugin(nologs)

        # start device before test start
        self._device_start()

        try:
            return self._run(opt, [runner, collector])
        finally:
            self._device_stop()

    def collect(self, testpath: str, reinit: bool = True) -> "Collected":
        """Collect tests.

        :param testpath: path to tests
        :param reinit: re-initialize pytest environment (default: True)
        """
        # initialize pytest env
        if reinit:  # pragma: no cover
            self._init_pytest(testpath)

        # start device so that test framework parsers (cmocka, gtest) can
        # query the binary for test names during pytest_generate_tests
        self._device_start()

        # collector plugin
        collector = CollectorPlugin(self._config, True)

        try:
            # run pytest with our custom collector plugin
            self._run([testpath], [collector])

            collected = Collected(
                collector.filtered, collector.skipped_items, collector.allitems
            )

            # return result
            return collected
        finally:
            self._device_stop()
