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

"""NTFC plugin configuration for pytest."""

import os
import time
from typing import TYPE_CHECKING, Any, Callable, Optional

import pytest

from ntfc.log.logger import logger

if TYPE_CHECKING:
    from ntfc.envconfig import EnvConfig


###############################################################################
# Class: PytestConfigPlugin
###############################################################################


class PytestConfigPlugin:
    """Everything you would have put in pytest.ini and conftest.py."""

    def __init__(self, config: "EnvConfig", verbose: bool = False) -> None:
        """Initialize custom pytest plugin.

        :param config: configuration instance
        """
        self._config = config
        self._verbose = verbose
        self._recovery_failed = False
        self._restart_gdb: Optional[Callable[[], None]] = None

    def set_restart_gdb(self, callback: "Callable[[], None]") -> None:
        """Register a callback fired after a successful device reboot.

        A reboot restarts every product's device process, so any GDB
        session already attached to one is left talking to a process
        that no longer exists. Set by
        :meth:`~ntfc.pytest.mypytest.MyPytest.runner` once the debug
        setup (and its GDB controllers, if any) exists.

        :param callback: Callable invoked with no arguments after a
            successful reboot.
        """
        self._restart_gdb = callback

    def _device_reboot(self) -> None:  # pragma: no cover
        """Reboot the device with retry and exponential back-off.

        Uses recovery configuration from EnvConfig (max_retries,
        base_delay, reboot_timeout).  Doubles the delay after each
        failed attempt, capped at 60 seconds.
        """
        recovery_cfg = self._config.recovery
        max_retries = recovery_cfg["max_retries"]
        delay = recovery_cfg["base_delay"]

        for attempt in range(1, max_retries + 1):
            logger.info(
                "Recovery attempt %d/%d (delay=%.1fs)",
                attempt,
                max_retries,
                delay if attempt > 1 else 0,
            )

            if attempt > 1:
                time.sleep(delay)
                delay = min(delay * 2, 60.0)

            try:
                success = pytest.product.reboot()
                if success:
                    logger.info("Device recovered on attempt %d", attempt)
                    if self._restart_gdb is not None:
                        self._restart_gdb()
                    return
                logger.warning("Reboot attempt %d returned failure", attempt)
            except Exception as exc:
                logger.error("Reboot attempt %d raised: %s", attempt, exc)

        logger.error("All %d recovery attempts failed", max_retries)
        self._recovery_failed = True

    def _generate_coredump_file(self, reason: Any) -> None:
        """Generate coredump file.

        :param reason:
        """
        # not supported yet

    def pytest_configure(self, config: pytest.Config) -> None:
        """Everything you would have put in pytest.ini.

        :param config: pytest config
        """
        # logging config
        config.option.log_cli = True

        if self._verbose:
            config.option.log_cli_level = "INFO"
        else:
            config.option.log_cli_level = "ERROR"

        result_dir = getattr(pytest, "result_dir", "")
        if result_dir:
            config.option.log_file = os.path.join(
                result_dir, "pytest.debug.log"
            )
            config.option.log_file_level = "DEBUG"
            config.option.log_file_format = (
                "%(asctime)s.%(msecs)03d %(levelname)s %(name)s:%(message)s"
            )
            config.option.log_file_date_format = "%Y-%m-%d %H:%M:%S"
            config.option.log_file_mode = "a"

        # custom markers (equivalent of markers= section)
        markers = [
            "monkey: Mark test to use the monkey plugin",
            "stability: Tests for stability verification",
            "performance: Tests for performance evaluation",
            "cmd_check: Check if specified commands are enabled",
            "dep_config: Check if macros are enabled in .config file",
            "extra_opts: Additional parameters for testing "
            "(e.g., --run_in_cores=cpu1,cpu2)",
            "config_value_check: Validate complex configuration strings",
        ]

        for m in markers:
            config.addinivalue_line("markers", m)

    def pytest_generate_tests(  # noqa: C901
        self, metafunc: pytest.Metafunc
    ) -> None:
        """Generate parametrized tests for multi-core execution.

        This hook handles parametrization of tests that use the 'core'
        fixture based on the @pytest.mark.extra_opts marker with
        --run_in_cores argument.

        Usage in test::

            @pytest.mark.extra_opts("--run_in_cores=cpu1,cpu2")
            def test_multi_core(core):
                # This test will run on cpu1 and cpu2
                pass

        :param metafunc: pytest metafunc object
        """
        # Skip if 'core' fixture not used
        if "core" not in metafunc.fixturenames:
            return

        # Check if test has @pytest.mark.parametrize
        has_parametrize_marker = any(
            marker.name == "parametrize"
            for marker in metafunc.definition.iter_markers("parametrize")
        )
        if has_parametrize_marker:
            return

        cores_opt = ""

        # Check if test has extra_opts marker with --run_in_cores
        for marker in metafunc.definition.own_markers:
            if marker.name == "extra_opts":
                for arg in marker.args:
                    if arg.startswith("--run_in_cores"):
                        cores_opt = arg.split("=", 1)[1]
                        break
                if cores_opt:
                    break

        # Parse cores list
        cores_list = [c.strip() for c in cores_opt.split(",") if c.strip()]

        # Default to main core if no cores specified
        if not cores_list:
            cores_list = ["main"]
            logger.warning(
                "No valid cores provided via --run_in_cores option, "
                "fallback to ['main']"
            )

        metafunc.parametrize("core", cores_list)

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        """Skip remaining tests if device recovery has failed.

        :param item: pytest item about to run
        """
        if self._recovery_failed:  # pragma: no cover
            pytest.skip("Device recovery failed, skipping remaining tests")

    @staticmethod
    def _failure_reason_from_product() -> tuple[bool, str, str]:
        """Return failure flags/reason from current product state.

        :return: Tuple of (has_failure, reason, longrepr_prefix).
        """
        if pytest.product.crash:
            return True, "crash", '"Device crashed"'
        if pytest.product.busyloop:
            return True, "busy_loop", '"Device busy_loop"'
        if pytest.product.flood:
            return True, "flood", '"Device flood"'
        if pytest.product.notalive:
            return True, "not_alive", '"Device not alive"'
        return False, "", ""

    @staticmethod
    def _is_crash_check_phase(
        item: pytest.Item, call: pytest.CallInfo[None]
    ) -> bool:
        """Check if crash state should be applied to this phase."""
        if call.when in ("setup", "call"):
            return True
        return call.when == "teardown" and not hasattr(
            item, "_setup_call_failed"
        )

    @staticmethod
    def _debug_wait_seconds(
        report_outcome: str, busyloop_crash_flag: bool
    ) -> int:
        """Return debug wait duration in seconds."""
        if report_outcome == "failed" and busyloop_crash_flag:
            return pytest.debug_time if hasattr(pytest, "debug_time") else 1800
        if report_outcome == "failed" and not busyloop_crash_flag:
            return 0
        return 0

    def pytest_runtest_makereport(
        self, item: pytest.Item, call: pytest.CallInfo[None]
    ) -> Any:
        """Create a TestReport for each of the runtest phases.

        On a crash this hook reboots the device via ``_device_reboot``.
        ``ntfc.pytest.coredump_plugin.CoredumpPlugin`` is marked
        ``hookimpl(hookwrapper=True, trylast=True)`` specifically so its
        post-yield coredump collection resumes before this hook's
        post-yield reboot; if that plugin's hook priority ever changes,
        collection can race the reboot and lose the coredump.

        :param item:
        :param call: the CallInfo for the phase
        """
        outcome = yield
        report = outcome.get_result()
        need_reboot = False
        need_coredump = False
        need_notify = False
        reason = "failed"
        busyloop_crash_flag = False
        flood_flag = False
        debug_time = 0

        logger.debug(
            f"pytest_runtest_makereport: {report.outcome}"
            f" loop {pytest.product.busyloop}  "
            f" crash {pytest.product.crash}"
            f" flood {pytest.product.flood}"
            f" notalive {pytest.product.notalive}"
        )

        has_failure, failure_reason, failure_longrepr = (
            self._failure_reason_from_product()
        )

        # Check for crashes in any phase
        if has_failure and self._is_crash_check_phase(item, call):
            logger.debug(f"pytest_runtest_makereport: {call.when}")

            # Mark the report as failed due to crash
            report.outcome = "failed"
            reason = failure_reason
            report.longrepr = (
                f"{failure_longrepr} detected, during: {call.when}"
            )

            # For setup phase, we need to prevent the test from running
            if call.when in ("setup", "call"):
                item._setup_call_failed = True

            need_coredump = True
            need_reboot = True
            need_notify = True
            busyloop_crash_flag = True

        if (
            report.outcome == "failed"
            and not busyloop_crash_flag
            and not flood_flag
        ):
            need_coredump = True
            reason = "failed"
            need_reboot = False

        # Notify users if test failed
        if (
            need_notify and hasattr(pytest, "notify") and pytest.result_dir
        ):  # pragma: no cover
            logger.info(
                f"Test {reason}, notifying developers for"
                f" on-site debugging ..."
            )
            pytest.notify.trigger_notify_with_more_info(pytest.result_dir)
            debug_time = self._debug_wait_seconds(
                report.outcome, busyloop_crash_flag
            )

        if need_coredump:
            # Handle core dump generation if needed
            self._generate_coredump_file(reason)

        if debug_time:  # pragma: no cover
            logger.info(f"Waiting {debug_time}s ...")
            time.sleep(debug_time)

        if need_reboot:  # pragma: no cover
            logger.info(f"Reboot device, reason: {report.longrepr}")
            self._device_reboot()

    @pytest.fixture  # type: ignore
    def switch_to_core(self, request: pytest.FixtureRequest) -> Any:
        """Switch to a specific core for SMP multi-core testing.

        This fixture is used in SMP mode to run tests on specific cores.
        It automatically switches back to the main core after the test.

        Usage::

            @pytest.mark.extra_opts("--run_in_cores=cpu1,cpu2")
            def test_multi_core(core):
                # Test will automatically run on cpu1 and cpu2
                # No need to manually switch, framework handles it
                pytest.product.sendCommand("test_command")

        For SMP mode only:

        - Checks if the product supports SMP
        - Validates that the target core exists
        - Switches to the target core before test execution
        - Automatically switches back to main core after test

        :param request: pytest request object
        :yield: None
        """
        # Get product from pytest session
        if not hasattr(pytest, "product") or not pytest.product:
            pytest.skip("Pytest does not have product object")

        product = pytest.product

        # Check if product supports SMP
        if not product.conf.is_smp:
            pytest.skip("Product is not in SMP mode")

        # Get the core parameter from the test
        core = getattr(request, "param", None)

        if not core:
            pytest.skip("No core specified for switching")

        # Validate core exists
        core_list = product.cores
        if not core_list:
            pytest.skip("Current product has no valid core list")

        if core not in core_list:
            pytest.skip(f"Current product does not have core: '{core}'")

        # Get main core (core0)
        main_core = core_list[0]
        switch_core_flag = False

        # Switch to target core if not already on main core
        if core != main_core:
            logger.info(f"Switching to core: {core}")

            # Use core0's device to switch cores
            ret = product.core(0).switch_core(core)

            if ret == 0:  # CmdStatus.SUCCESS
                switch_core_flag = True
                logger.info(f"Successfully switched to core: {core}")
            else:
                pytest.skip(f"Failed to switch to core {core}")
        else:
            logger.info(f"Already on main core: {main_core}")

        yield

        # Switch back to main core after test
        if switch_core_flag:
            logger.info(f"Switching back to main core: {main_core}")
            ret = product.core(0).switch_core(main_core)

            if ret != 0:  # CmdStatus.SUCCESS
                logger.warning(
                    f"Failed to switch back to main core {main_core}"
                )
