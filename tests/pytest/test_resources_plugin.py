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

"""Tests for the resources pytest plugin."""

import logging
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from ntfc.device.cmds import CmdReturn, CmdStatus
from ntfc.envconfig import EnvConfig
from ntfc.pytest.resources_plugin import ResourcePlugin
from ntfc.resmon.monitor import ResourceLeakError

FREE_HDR = (
    "      total       used       free    maxused    maxfree  nused  nfree"
    " name\n"
)
FREE_A = FREE_HDR + "   1000   100   900   100   900   6   3 Umem\n"
FREE_B = FREE_HDR + "   1000   116   884   116   884   7   3 Umem\n"
PS_A = "  TID   PID COMMAND\n    4     4 nsh_main\n"
FD_A = "FD  OFLAGS  TYPE POS PATH\n0   2       1    0   /dev/console\n"

KV_ALL = {
    "CONFIG_FS_PROCFS": True,
    "CONFIG_MM_IOB": True,
    "CONFIG_NET": True,
}


def _core(name: str, script: Dict[str, List[str]]) -> MagicMock:
    core = MagicMock()
    core.name = name
    core.prompt = b"nsh> "
    core.calls: List[str] = []

    def send(cmd: str, timeout: int = 30) -> CmdReturn:
        core.calls.append(cmd)
        outputs = script[cmd]
        out = outputs.pop(0) if len(outputs) > 1 else outputs[0]
        return CmdReturn(CmdStatus.SUCCESS, None, f"{cmd}\r\n{out}nsh> ")

    core.sendCommandReadUntilPattern.side_effect = send
    return core


def _product(
    name: str = "prod",
    kv: Dict[str, Any] = KV_ALL,
    script: Dict[str, List[str]] | None = None,
    cores: int = 1,
    smp: bool = False,
) -> MagicMock:
    script = script or {"free": [FREE_A], "ps": [PS_A]}
    product = MagicMock()
    product.name = name
    product.crash = False
    product.busyloop = False
    product.flood = False
    product.notalive = False
    product.conf.kv_check.side_effect = lambda sym, core=0: kv.get(sym, False)
    product.conf.primary_test_core_index = 0
    product.conf.active_core_indices = list(range(cores))
    product.conf.is_smp = smp
    product_cores = [
        _core("main" if i == 0 else f"cpu{i}", dict(script))
        for i in range(cores)
    ]
    product.core.side_effect = lambda i=0: product_cores[i]
    product.test_cores = product_cores
    return product


def _config(resources: Dict[str, Any] | None = None) -> EnvConfig:
    cfg: Dict[str, Any] = {
        "config": {},
        "product": {"name": "prod", "cores": {}},
    }
    if resources is not None:
        cfg["config"]["resources"] = resources
    return EnvConfig(cfg)


def _request(marker_kwargs: Dict[str, Any] | None = None) -> MagicMock:
    request = MagicMock()
    request.node.user_properties = []
    marker = None
    if marker_kwargs is not None:
        marker = MagicMock()
        marker.kwargs = marker_kwargs
    request.node.get_closest_marker.return_value = marker
    return request


def _fixture_gen(plugin: ResourcePlugin, request: MagicMock) -> Any:
    """Return the unwrapped resources fixture generator."""
    fixture = ResourcePlugin.resources.__wrapped__  # type: ignore
    return fixture(plugin, request)


def _run_fixture(plugin: ResourcePlugin, request: MagicMock) -> Any:
    """Drive the resources fixture through setup and teardown."""
    gen = _fixture_gen(plugin, request)
    monitor = next(gen)
    try:
        next(gen)
    except StopIteration:
        pass
    return monitor


class TestEnvConfigResources:
    def test_defaults(self) -> None:
        assert _config().resources == {
            "enabled": False,
            "probes": ["tasks", "fds"],
            "settle_retries": 3,
            "settle_delay": 1.0,
            "heap_tolerance": 0,
            "cpuload_max": 10,
        }

    def test_merge(self) -> None:
        cfg = _config({"enabled": True, "probes": ["heap"]})
        assert cfg.resources["enabled"] is True
        assert cfg.resources["probes"] == ["heap"]
        assert cfg.resources["settle_retries"] == 3


class TestProbeSelection:
    def test_disabled_is_inactive(self) -> None:
        product = _product()
        plugin = ResourcePlugin(_config({"enabled": False}), [product])
        assert plugin.monitor(None).active is False
        assert product.test_cores[0].calls == []

    def test_missing_procfs_is_inactive(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        product = _product(kv={})
        plugin = ResourcePlugin(_config({"enabled": True}), [product])
        with caplog.at_level(logging.WARNING):
            assert plugin.monitor(None).active is False
        assert "CONFIG_FS_PROCFS" in caplog.text

    def test_default_probes(self) -> None:
        plugin = ResourcePlugin(_config({"enabled": True}), [_product()])
        assert plugin.probe_names(None) == ["tasks", "fds"]

    def test_gated_probe_dropped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        kv = {**KV_ALL, "CONFIG_FS_PROCFS_EXCLUDE_PROCESS": True}
        plugin = ResourcePlugin(_config({"enabled": True}), [_product(kv=kv)])
        with caplog.at_level(logging.WARNING):
            assert plugin.probe_names(None) == []
        assert "'tasks'" in caplog.text
        assert "'fds'" in caplog.text
        assert "CONFIG_FS_PROCFS_EXCLUDE_PROCESS" in caplog.text

    def test_probe_must_be_available_on_every_product(self) -> None:
        kv = {**KV_ALL, "CONFIG_NSH_DISABLE_PS": True}
        plugin = ResourcePlugin(
            _config({"enabled": True}), [_product("a"), _product("b", kv=kv)]
        )
        assert plugin.probe_names(None) == ["fds"]

    def test_marker_overrides_probes(self) -> None:
        plugin = ResourcePlugin(_config({"enabled": True}), [_product()])
        marker = MagicMock()
        marker.kwargs = {"probes": ["heap"]}
        assert plugin.probe_names(marker) == ["heap"]

    def test_unknown_probe_in_config(self) -> None:
        plugin = ResourcePlugin(
            _config({"enabled": True, "probes": ["nope"]}), [_product()]
        )
        with pytest.raises(ValueError, match="nope"):
            plugin.probe_names(None)


class TestTargets:
    def test_amp_samples_every_active_core(self) -> None:
        product = _product(cores=2)
        plugin = ResourcePlugin(_config({"enabled": True}), [product])
        targets = plugin.targets()
        assert sorted(targets) == ["prod/cpu1", "prod/main"]

    def test_smp_samples_primary_core_only(self) -> None:
        product = _product(cores=2, smp=True)
        plugin = ResourcePlugin(_config({"enabled": True}), [product])
        assert list(plugin.targets()) == ["prod/main"]

    def test_sampler_cleans_output(self) -> None:
        product = _product()
        plugin = ResourcePlugin(_config({"enabled": True}), [product])
        send = plugin.targets()["prod/main"]
        assert send("free") == FREE_A
        assert product.test_cores[0].calls == ["free"]


class TestFixture:
    def test_clean_test_passes_and_records(self) -> None:
        product = _product(
            script={
                "free": [FREE_A],
                "ps": [PS_A],
                "cat /proc/self/group/fd": [FD_A],
            }
        )
        plugin = ResourcePlugin(_config({"enabled": True}), [product])
        request = _request()
        monitor = _run_fixture(plugin, request)
        assert monitor.active is True
        assert request.node.user_properties == [("resources", {})]
        assert product.test_cores[0].calls.count("ps") == 2

    def test_leak_raises_and_logs(self) -> None:
        product = _product(script={"free": [FREE_A, FREE_B]})
        plugin = ResourcePlugin(
            _config(
                {"enabled": True, "probes": ["heap"], "settle_retries": 0}
            ),
            [product],
        )
        request = _request()
        with pytest.raises(ResourceLeakError, match="Umem used 100 -> 116"):
            _run_fixture(plugin, request)
        key, diff = request.node.user_properties[0]
        assert key == "resources"
        assert diff["prod/main"]["heap"][0] == "Umem used 100 -> 116 (+16)"
        product.test_cores[0].device.log_event.assert_called()
        msg = product.test_cores[0].device.log_event.call_args[0][0]
        assert "heap" in msg and "Umem" in msg

    def test_unhealthy_product_skips_check(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        product = _product(script={"free": [FREE_A, FREE_B]})
        plugin = ResourcePlugin(
            _config({"enabled": True, "probes": ["heap"]}), [product]
        )
        request = _request()
        gen = _fixture_gen(plugin, request)
        next(gen)
        product.crash = True
        with caplog.at_level(logging.WARNING):
            with pytest.raises(StopIteration):
                next(gen)
        assert "skipping" in caplog.text
        assert request.node.user_properties == []
        assert product.test_cores[0].calls == ["free"]

    def test_disabled_fixture_is_noop(self) -> None:
        product = _product()
        plugin = ResourcePlugin(_config(), [product])
        request = _request()
        monitor = _run_fixture(plugin, request)
        assert monitor.active is False
        assert product.test_cores[0].calls == []
        assert request.node.user_properties == []

    def test_marker_tolerance_applies(self) -> None:
        product = _product(script={"free": [FREE_A, FREE_B]})
        plugin = ResourcePlugin(
            _config(
                {"enabled": True, "probes": ["heap"], "settle_retries": 0}
            ),
            [product],
        )
        request = _request({"heap_tolerance": 100})
        with pytest.raises(ResourceLeakError) as exc:
            _run_fixture(plugin, request)
        assert "nused" in str(exc.value)
        assert " used " not in str(exc.value)
