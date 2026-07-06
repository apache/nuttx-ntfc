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

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest as pytest

from ntfc.pytest.configure import PytestConfigPlugin


def test_test_pytestconfigureplugin_init(config_dummy):

    _ = PytestConfigPlugin(config_dummy)


def test_set_restart_gdb_stores_callback(config_dummy):
    plugin = PytestConfigPlugin(config_dummy)
    assert plugin._restart_gdb is None

    callback = MagicMock()
    plugin.set_restart_gdb(callback)

    assert plugin._restart_gdb is callback


def test_pytest_configure_log_file_uses_result_dir(
    config_dummy, monkeypatch, tmp_path
):
    """Test pytest_configure sets log_file inside result_dir when available."""
    monkeypatch.setattr(pytest, "result_dir", str(tmp_path), raising=False)

    plugin = PytestConfigPlugin(config_dummy)
    mock_config = MagicMock()
    mock_config.option = MagicMock()
    plugin.pytest_configure(mock_config)

    assert mock_config.option.log_file == os.path.join(
        str(tmp_path), "pytest.debug.log"
    )


def test_pytest_configure_no_log_file_without_result_dir(
    config_dummy, monkeypatch
):
    """Test pytest_configure skips log_file when result_dir is not set."""
    monkeypatch.setattr(pytest, "result_dir", "", raising=False)

    plugin = PytestConfigPlugin(config_dummy)
    mock_config = MagicMock()
    mock_config.option = MagicMock()
    plugin.pytest_configure(mock_config)

    # log_file_level is only set alongside log_file; if result_dir is empty
    # the whole block is skipped — attribute stays a MagicMock, not "DEBUG"
    assert mock_config.option.log_file_level != "DEBUG"


def test_pytest_generate_tests_with_core_fixture(config_dummy, monkeypatch):
    """Test pytest_generate_tests with core fixture."""
    # Mock metafunc
    metafunc = MagicMock()
    metafunc.fixturenames = ["core"]
    metafunc.definition = MagicMock()
    metafunc.definition.iter_markers = MagicMock(return_value=[])
    metafunc.definition.own_markers = []

    plugin = PytestConfigPlugin(config_dummy)
    plugin.pytest_generate_tests(metafunc)

    # Should parametrize with default ['main'] when no --run_in_cores
    metafunc.parametrize.assert_called_once_with("core", ["main"])


def test_pytest_generate_tests_with_extra_opts(config_dummy, monkeypatch):
    """Test pytest_generate_tests with --run_in_cores marker."""
    # Mock metafunc
    metafunc = MagicMock()
    metafunc.fixturenames = ["core"]
    metafunc.definition = MagicMock()
    metafunc.definition.iter_markers = MagicMock(return_value=[])

    # Create marker with --run_in_cores
    marker = MagicMock()
    marker.name = "extra_opts"
    marker.args = ["--run_in_cores=main,cpu1,cpu2"]
    metafunc.definition.own_markers = [marker]

    plugin = PytestConfigPlugin(config_dummy)
    plugin.pytest_generate_tests(metafunc)

    # Should parametrize with ['main', 'cpu1', 'cpu2']
    metafunc.parametrize.assert_called_once_with(
        "core", ["main", "cpu1", "cpu2"]
    )


def test_pytest_generate_tests_markers_edge_cases(config_dummy, monkeypatch):
    """Test pytest_generate_tests with various marker edge cases."""
    plugin = PytestConfigPlugin(config_dummy)

    # Test with non-extra_opts marker (branch 127->131)
    metafunc = MagicMock()
    metafunc.fixturenames = ["core"]
    metafunc.definition = MagicMock()
    metafunc.definition.iter_markers = MagicMock(return_value=[])
    marker = MagicMock()
    marker.name = "some_other_marker"
    metafunc.definition.own_markers = [marker]
    plugin.pytest_generate_tests(metafunc)
    metafunc.parametrize.assert_called_once_with("core", ["main"])

    # Test with extra_opts but wrong arg (branch 128->127)
    metafunc = MagicMock()
    metafunc.fixturenames = ["core"]
    metafunc.definition = MagicMock()
    metafunc.definition.iter_markers = MagicMock(return_value=[])
    marker = MagicMock()
    marker.name = "extra_opts"
    marker.args = ["--some_other_option=value"]
    metafunc.definition.own_markers = [marker]
    plugin.pytest_generate_tests(metafunc)
    metafunc.parametrize.assert_called_once_with("core", ["main"])

    # Test with multiple markers triggering break (branch 131->125)
    metafunc = MagicMock()
    metafunc.fixturenames = ["core"]
    metafunc.definition = MagicMock()
    metafunc.definition.iter_markers = MagicMock(return_value=[])
    marker1 = MagicMock()
    marker1.name = "some_other_marker"
    marker2 = MagicMock()
    marker2.name = "extra_opts"
    marker2.args = ["--run_in_cores=cpu1"]
    metafunc.definition.own_markers = [marker1, marker2]
    plugin.pytest_generate_tests(metafunc)
    metafunc.parametrize.assert_called_once_with("core", ["cpu1"])


def test_pytest_generate_tests_without_core_fixture(config_dummy, monkeypatch):
    """Test pytest_generate_tests without core fixture."""
    metafunc = MagicMock()
    metafunc.fixturenames = ["other_fixture"]

    plugin = PytestConfigPlugin(config_dummy)
    plugin.pytest_generate_tests(metafunc)

    # Should not parametrize if core fixture not used
    metafunc.parametrize.assert_not_called()


def test_pytest_generate_tests_with_parametrize_marker(
    config_dummy, monkeypatch
):
    """Test pytest_generate_tests with parametrize marker returns early."""
    metafunc = MagicMock()
    metafunc.fixturenames = ["core"]
    metafunc.definition = MagicMock()

    # Mock iter_markers to return a parametrize marker
    mock_param_marker = MagicMock()
    mock_param_marker.name = "parametrize"
    metafunc.definition.iter_markers = MagicMock(
        return_value=[mock_param_marker]
    )

    plugin = PytestConfigPlugin(config_dummy)
    plugin.pytest_generate_tests(metafunc)

    # Should not parametrize if test already has @pytest.mark.parametrize
    metafunc.parametrize.assert_not_called()


def test_switch_to_core_fixture_no_product_object(config_dummy, monkeypatch):
    """Test switch_to_core fixture skips when no product object."""
    import pytest as real_pytest

    mock_pytest = MagicMock()
    mock_pytest.skip = real_pytest.skip
    # Explicitly set product to None/Falsy value
    mock_pytest.product = None
    monkeypatch.setattr("ntfc.pytest.configure.pytest", mock_pytest)

    plugin = PytestConfigPlugin(config_dummy)

    request = MagicMock()
    request.param = "main"

    unwrapped = plugin.switch_to_core.__wrapped__  # type: ignore
    gen = unwrapped(plugin, request)

    with pytest.raises(
        pytest.skip.Exception, match="Pytest does not have product object"
    ):
        next(gen)


def test_switch_to_core_fixture_not_smp(config_dummy, monkeypatch):
    """Test switch_to_core fixture skips when not SMP."""
    # Mock pytest but keep real skip function
    import pytest as real_pytest

    mock_pytest = MagicMock()
    mock_pytest.skip = real_pytest.skip  # Use real skip to raise exception
    monkeypatch.setattr("ntfc.pytest.configure.pytest", mock_pytest)

    # Create non-SMP product
    mock_product = MagicMock()
    mock_conf = MagicMock()
    mock_conf.is_smp = False
    mock_product.conf = mock_conf
    mock_pytest.product = mock_product

    plugin = PytestConfigPlugin(config_dummy)

    # Create mock request
    request = MagicMock()

    # Get the unwrapped function (bypass pytest.fixture decorator)
    unwrapped = plugin.switch_to_core.__wrapped__  # type: ignore

    # Get the generator and advance it to trigger the skip
    gen = unwrapped(plugin, request)

    # Should skip when not SMP
    with pytest.raises(
        pytest.skip.Exception, match="Product is not in SMP mode"
    ):
        next(gen)


def test_switch_to_core_fixture_no_core_param(config_dummy, monkeypatch):
    """Test switch_to_core fixture skips when no core param."""
    # Mock pytest but keep real skip function
    import pytest as real_pytest

    mock_pytest = MagicMock()
    mock_pytest.skip = real_pytest.skip  # Use real skip to raise exception
    monkeypatch.setattr("ntfc.pytest.configure.pytest", mock_pytest)

    # Create SMP product
    mock_product = MagicMock()
    mock_conf = MagicMock()
    mock_conf.is_smp = True
    mock_product.cores = ["main", "cpu1"]
    mock_product.conf = mock_conf
    mock_pytest.product = mock_product

    plugin = PytestConfigPlugin(config_dummy)

    # Create mock request without param
    request = MagicMock()
    request.param = None

    # Get the unwrapped function (bypass pytest.fixture decorator)
    unwrapped = plugin.switch_to_core.__wrapped__  # type: ignore

    # Get the generator and advance it to trigger the skip
    gen = unwrapped(plugin, request)

    # Should skip when no core param
    with pytest.raises(pytest.skip.Exception, match="No core specified"):
        next(gen)


def test_switch_to_core_fixture_no_core_list(config_dummy, monkeypatch):
    """Test switch_to_core fixture skips when no valid core list."""
    import pytest as real_pytest

    mock_pytest = MagicMock()
    mock_pytest.skip = real_pytest.skip
    monkeypatch.setattr("ntfc.pytest.configure.pytest", mock_pytest)

    # Create SMP product with empty cores list
    mock_product = MagicMock()
    mock_conf = MagicMock()
    mock_conf.is_smp = True
    mock_product.cores = []
    mock_product.conf = mock_conf
    mock_pytest.product = mock_product

    plugin = PytestConfigPlugin(config_dummy)

    request = MagicMock()
    request.param = "main"

    unwrapped = plugin.switch_to_core.__wrapped__  # type: ignore
    gen = unwrapped(plugin, request)

    with pytest.raises(
        pytest.skip.Exception, match="Current product has no valid core list"
    ):
        next(gen)


def test_switch_to_core_fixture_core_not_in_list(config_dummy, monkeypatch):
    """Test switch_to_core fixture skips when core not in list."""
    import pytest as real_pytest

    mock_pytest = MagicMock()
    mock_pytest.skip = real_pytest.skip
    monkeypatch.setattr("ntfc.pytest.configure.pytest", mock_pytest)

    # Create SMP product
    mock_product = MagicMock()
    mock_conf = MagicMock()
    mock_conf.is_smp = True
    mock_product.cores = ["main", "cpu1"]
    mock_product.conf = mock_conf
    mock_pytest.product = mock_product

    plugin = PytestConfigPlugin(config_dummy)

    request = MagicMock()
    request.param = "cpu99"  # Core not in list

    unwrapped = plugin.switch_to_core.__wrapped__  # type: ignore
    gen = unwrapped(plugin, request)

    with pytest.raises(
        pytest.skip.Exception,
        match="Current product does not have core: 'cpu99'",
    ):
        next(gen)


def test_switch_to_core_fixture_main_core(config_dummy, monkeypatch):
    """Test switch_to_core fixture when already on main core."""
    import pytest as real_pytest

    mock_pytest = MagicMock()
    mock_pytest.skip = real_pytest.skip
    monkeypatch.setattr("ntfc.pytest.configure.pytest", mock_pytest)

    # Create SMP product
    mock_product = MagicMock()
    mock_conf = MagicMock()
    mock_conf.is_smp = True
    mock_product.cores = ["main", "cpu1"]
    mock_product.conf = mock_conf
    mock_pytest.product = mock_product

    plugin = PytestConfigPlugin(config_dummy)

    request = MagicMock()
    request.param = "main"  # Already on main core

    unwrapped = plugin.switch_to_core.__wrapped__  # type: ignore
    gen = unwrapped(plugin, request)

    # Should not raise, just yield
    result = next(gen)
    assert result is None

    # Clean up the generator
    try:
        next(gen)
    except StopIteration:
        pass


def test_switch_to_core_fixture_switch_success(config_dummy, monkeypatch):
    """Test switch_to_core fixture when core switch succeeds."""
    import pytest as real_pytest

    mock_pytest = MagicMock()
    mock_pytest.skip = real_pytest.skip
    monkeypatch.setattr("ntfc.pytest.configure.pytest", mock_pytest)

    # Create SMP product with mock core
    mock_core0 = MagicMock()
    mock_core0.switch_core.return_value = 0  # Success

    mock_product = MagicMock()
    mock_conf = MagicMock()
    mock_conf.is_smp = True
    mock_product.cores = ["main", "cpu1"]
    mock_product.conf = mock_conf
    mock_product.core = MagicMock(return_value=mock_core0)
    mock_pytest.product = mock_product

    plugin = PytestConfigPlugin(config_dummy)

    request = MagicMock()
    request.param = "cpu1"

    unwrapped = plugin.switch_to_core.__wrapped__  # type: ignore
    gen = unwrapped(plugin, request)

    # Should not raise, just yield after switching
    result = next(gen)
    assert result is None

    # Verify switch was called
    mock_core0.switch_core.assert_called_once_with("cpu1")

    # Clean up the generator
    try:
        next(gen)
    except StopIteration:
        pass


def test_switch_to_core_fixture_switch_failure(config_dummy, monkeypatch):
    """Test switch_to_core fixture when core switch fails."""
    import pytest as real_pytest

    mock_pytest = MagicMock()
    mock_pytest.skip = real_pytest.skip
    monkeypatch.setattr("ntfc.pytest.configure.pytest", mock_pytest)

    # Create SMP product with mock core
    mock_core0 = MagicMock()
    mock_core0.switch_core.return_value = -1  # Failure

    mock_product = MagicMock()
    mock_conf = MagicMock()
    mock_conf.is_smp = True
    mock_product.cores = ["main", "cpu1"]
    mock_product.conf = mock_conf
    mock_product.core = MagicMock(return_value=mock_core0)
    mock_pytest.product = mock_product

    plugin = PytestConfigPlugin(config_dummy)

    request = MagicMock()
    request.param = "cpu1"

    unwrapped = plugin.switch_to_core.__wrapped__  # type: ignore
    gen = unwrapped(plugin, request)

    with pytest.raises(
        pytest.skip.Exception, match="Failed to switch to core cpu1"
    ):
        next(gen)


def test_switch_to_core_fixture_switch_back_failure(config_dummy, monkeypatch):
    """Test switch_to_core fixture when switching back to main core fails."""
    import pytest as real_pytest

    mock_pytest = MagicMock()
    mock_pytest.skip = real_pytest.skip
    monkeypatch.setattr("ntfc.pytest.configure.pytest", mock_pytest)

    # Create SMP product with mock core
    mock_core0 = MagicMock()
    # First switch succeeds (to cpu1), switch back fails
    mock_core0.switch_core.side_effect = [0, -1]

    mock_product = MagicMock()
    mock_conf = MagicMock()
    mock_conf.is_smp = True
    mock_product.cores = ["main", "cpu1"]
    mock_product.conf = mock_conf
    mock_product.core = MagicMock(return_value=mock_core0)
    mock_pytest.product = mock_product

    plugin = PytestConfigPlugin(config_dummy)

    request = MagicMock()
    request.param = "cpu1"

    unwrapped = plugin.switch_to_core.__wrapped__  # type: ignore
    gen = unwrapped(plugin, request)

    # Should not raise, just yield after switching
    result = next(gen)
    assert result is None

    # Verify first switch was called
    mock_core0.switch_core.assert_called_with("cpu1")

    # Trigger cleanup by advancing generator (switch back fails,
    # but doesn't raise)
    try:
        next(gen)
    except StopIteration:
        pass

    # Verify switch back was attempted (second call)
    assert mock_core0.switch_core.call_count == 2


def _run_makereport_hook(plugin, item, call, report):
    outcome = MagicMock()
    outcome.get_result.return_value = report
    gen = plugin.pytest_runtest_makereport(item, call)
    next(gen)
    with pytest.raises(StopIteration):
        gen.send(outcome)


def test_failure_reason_from_product_variants(config_dummy, monkeypatch):
    plugin = PytestConfigPlugin(config_dummy)

    cases = [
        (
            SimpleNamespace(
                crash=True, busyloop=False, flood=False, notalive=False
            ),
            (True, "crash", '"Device crashed"'),
        ),
        (
            SimpleNamespace(
                crash=False, busyloop=True, flood=False, notalive=False
            ),
            (True, "busy_loop", '"Device busy_loop"'),
        ),
        (
            SimpleNamespace(
                crash=False, busyloop=False, flood=True, notalive=False
            ),
            (True, "flood", '"Device flood"'),
        ),
        (
            SimpleNamespace(
                crash=False, busyloop=False, flood=False, notalive=True
            ),
            (True, "not_alive", '"Device not alive"'),
        ),
        (
            SimpleNamespace(
                crash=False, busyloop=False, flood=False, notalive=False
            ),
            (False, "", ""),
        ),
    ]

    for product, expected in cases:
        fake_pytest = SimpleNamespace(product=product)
        monkeypatch.setattr("ntfc.pytest.configure.pytest", fake_pytest)
        assert plugin._failure_reason_from_product() == expected


def test_is_crash_check_phase(config_dummy):
    plugin = PytestConfigPlugin(config_dummy)
    item = SimpleNamespace()

    assert plugin._is_crash_check_phase(item, SimpleNamespace(when="setup"))
    assert plugin._is_crash_check_phase(item, SimpleNamespace(when="call"))
    assert plugin._is_crash_check_phase(item, SimpleNamespace(when="teardown"))

    item2 = SimpleNamespace(_setup_call_failed=True)
    assert not plugin._is_crash_check_phase(
        item2, SimpleNamespace(when="teardown")
    )


def test_debug_wait_seconds_variants(config_dummy, monkeypatch):
    plugin = PytestConfigPlugin(config_dummy)

    fake_pytest = SimpleNamespace(debug_time=7)
    monkeypatch.setattr("ntfc.pytest.configure.pytest", fake_pytest)
    assert plugin._debug_wait_seconds("failed", True) == 7
    assert plugin._debug_wait_seconds("failed", False) == 0
    assert plugin._debug_wait_seconds("passed", True) == 0

    fake_pytest2 = SimpleNamespace()
    monkeypatch.setattr("ntfc.pytest.configure.pytest", fake_pytest2)
    assert plugin._debug_wait_seconds("failed", True) == 1800


def test_pytest_runtest_makereport_crash_path(config_dummy, monkeypatch):
    product = SimpleNamespace(
        crash=True, busyloop=False, flood=False, notalive=False
    )
    fake_pytest = SimpleNamespace(product=product, result_dir="")
    monkeypatch.setattr("ntfc.pytest.configure.pytest", fake_pytest)

    plugin = PytestConfigPlugin(config_dummy)
    plugin._generate_coredump_file = MagicMock()
    plugin._device_reboot = MagicMock()

    item = SimpleNamespace()
    call = SimpleNamespace(when="call")
    report = SimpleNamespace(outcome="passed", longrepr="")

    _run_makereport_hook(plugin, item, call, report)

    assert report.outcome == "failed"
    assert report.longrepr == '"Device crashed" detected, during: call'
    assert getattr(item, "_setup_call_failed", False) is True
    plugin._generate_coredump_file.assert_called_once_with("crash")
    plugin._device_reboot.assert_called_once()


def test_pytest_runtest_makereport_crash_teardown_path(
    config_dummy, monkeypatch
):
    product = SimpleNamespace(
        crash=True, busyloop=False, flood=False, notalive=False
    )
    fake_pytest = SimpleNamespace(product=product, result_dir="")
    monkeypatch.setattr("ntfc.pytest.configure.pytest", fake_pytest)

    plugin = PytestConfigPlugin(config_dummy)
    plugin._generate_coredump_file = MagicMock()
    plugin._device_reboot = MagicMock()

    item = SimpleNamespace()
    call = SimpleNamespace(when="teardown")
    report = SimpleNamespace(outcome="passed", longrepr="")

    _run_makereport_hook(plugin, item, call, report)

    assert report.outcome == "failed"
    assert not hasattr(item, "_setup_call_failed")
    plugin._generate_coredump_file.assert_called_once_with("crash")
    plugin._device_reboot.assert_called_once()
