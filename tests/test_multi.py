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
import textwrap
import threading
import time
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree

import pytest

from ntfc.multi import (
    ManifestConfig,
    MultiOptions,
    MultiSessionRunner,
    SessionConfig,
    SessionResult,
)


def _write_yaml(tmp: str, name: str, content: str) -> str:
    """Write a YAML file in tmp dir and return its path."""
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        f.write(textwrap.dedent(content))
    return path


def _write_config_yaml(tmp: str, name: str = "config.yaml") -> str:
    """Write a minimal NTFC config YAML and return its path."""
    return _write_yaml(
        tmp,
        name,
        """\
        config:
          cwd: './external'
          build_dir: './build'
        product:
          name: "test-product"
          cores:
            core0:
              name: 'main'
              device: 'sim'
        """,
    )


def _write_manifest(
    tmp: str,
    confpath: str,
    testpath: str,
    extra: str = "",
) -> str:
    """Write a valid manifest YAML referencing given paths."""
    return _write_yaml(
        tmp,
        "manifest.yaml",
        f"""\
        options:
          fail_fast: false
          parallel: false
        sessions:
          - name: "session-a"
            confpath: "{confpath}"
            testpath: "{testpath}"
        {extra}
        """,
    )


def _make_runner(
    manifest: ManifestConfig,
    rebuild: bool = False,
) -> MultiSessionRunner:
    """Create a MultiSessionRunner with common defaults."""
    return MultiSessionRunner(
        manifest, rebuild=rebuild, verbose=False, debug=False
    )


def _make_junit_xml(path: str, suite_name: str, tests: int) -> None:
    """Create a minimal JUnit XML file."""
    root = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(root, "testsuite")
    suite.set("name", suite_name)
    suite.set("tests", str(tests))
    suite.set("failures", "0")
    suite.set("errors", "0")
    suite.set("skipped", "0")
    suite.set("time", "1.0")

    for i in range(tests):
        tc = ElementTree.SubElement(suite, "testcase")
        tc.set("name", f"test_{i}")
        tc.set("classname", f"{suite_name}::TestClass")
        tc.set("time", "0.5")

    tree = ElementTree.ElementTree(root)
    tree.write(path)


def _write_report_xml(result_dir: str, xml: str) -> None:
    """Write a report.xml file in result_dir."""
    os.makedirs(result_dir, exist_ok=True)
    with open(os.path.join(result_dir, "report.xml"), "w") as f:
        f.write(xml)


def test_session_config_defaults():
    sc = SessionConfig(name="x", confpath="a", testpath="b")
    assert sc.resources == []
    assert sc.exitonfail is None
    assert sc.loops is None
    assert sc.timeout is None
    assert sc.timeout_session is None
    assert sc.modules is None


def test_multi_options_defaults():
    mo = MultiOptions()
    assert mo.fail_fast is False
    assert mo.parallel is False


def test_session_result_fields():
    sr = SessionResult(name="s", exit_code=0, result_dir="/tmp")
    assert sr.name == "s"
    assert sr.exit_code == 0
    assert sr.result_dir == "/tmp"


def test_load_valid(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)
    manifest_path = _write_manifest(tmp, confpath, tmp)

    mc = ManifestConfig.load(manifest_path)

    assert mc.options.fail_fast is False
    assert mc.options.parallel is False
    assert len(mc.sessions) == 1
    assert mc.sessions[0].name == "session-a"
    assert mc.sessions[0].confpath == confpath
    assert mc.sessions[0].testpath == tmp


def test_load_not_mapping(tmp_path):
    path = _write_yaml(str(tmp_path), "bad.yaml", "- list\n- item\n")
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        ManifestConfig.load(path)


def test_load_bad_options(tmp_path):
    path = _write_yaml(
        str(tmp_path),
        "bad.yaml",
        """\

        options: "string"
        sessions:
          - name: x
            confpath: y
            testpath: z
        """,
    )
    with pytest.raises(ValueError, match="'options' must be a mapping"):
        ManifestConfig.load(path)


def test_load_empty_sessions(tmp_path):
    path = _write_yaml(str(tmp_path), "bad.yaml", "sessions: []\n")
    with pytest.raises(ValueError, match="non-empty list"):
        ManifestConfig.load(path)


def test_load_sessions_not_list(tmp_path):
    path = _write_yaml(str(tmp_path), "bad.yaml", 'sessions: "string"\n')
    with pytest.raises(ValueError, match="non-empty list"):
        ManifestConfig.load(path)


def test_load_session_not_mapping(tmp_path):
    path = _write_yaml(
        str(tmp_path),
        "bad.yaml",
        """\

        sessions:
          - "just a string"
        """,
    )
    with pytest.raises(ValueError, match="session 0 must be a mapping"):
        ManifestConfig.load(path)


def test_load_session_missing_name(tmp_path):
    path = _write_yaml(
        str(tmp_path),
        "bad.yaml",
        """\

        sessions:
          - confpath: x
            testpath: y
        """,
    )
    with pytest.raises(ValueError, match="'name' is required"):
        ManifestConfig.load(path)


def test_load_duplicate_name(tmp_path):
    path = _write_yaml(
        str(tmp_path),
        "bad.yaml",
        """\

        sessions:
          - name: dup
            confpath: x
            testpath: y
          - name: dup
            confpath: a
            testpath: b
        """,
    )
    with pytest.raises(ValueError, match="duplicate session name"):
        ManifestConfig.load(path)


def test_load_session_missing_confpath(tmp_path):
    path = _write_yaml(
        str(tmp_path),
        "bad.yaml",
        """\

        sessions:
          - name: x
            testpath: y
        """,
    )
    with pytest.raises(ValueError, match="'confpath' is required"):
        ManifestConfig.load(path)


def test_load_session_missing_testpath(tmp_path):
    path = _write_yaml(
        str(tmp_path),
        "bad.yaml",
        """\

        sessions:
          - name: x
            confpath: y
        """,
    )
    with pytest.raises(ValueError, match="'testpath' is required"):
        ManifestConfig.load(path)


def test_load_session_bad_resources(tmp_path):
    path = _write_yaml(
        str(tmp_path),
        "bad.yaml",
        """\

        sessions:
          - name: x
            confpath: y
            testpath: z
            resources: "string"
        """,
    )
    with pytest.raises(ValueError, match="'resources' must be a list"):
        ManifestConfig.load(path)


def test_load_with_resources_and_overrides(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)
    path = _write_yaml(
        tmp,
        "manifest.yaml",
        f"""\

        sessions:
          - name: s1
            confpath: "{confpath}"
            testpath: "{tmp}"
            resources: [vcan0, tap0]
            exitonfail: true
            loops: 3
            timeout: 300
            timeout_session: 7200
            modules: "nsh"
        """,
    )

    mc = ManifestConfig.load(path)
    s = mc.sessions[0]
    assert s.resources == ["vcan0", "tap0"]
    assert s.exitonfail is True
    assert s.loops == 3
    assert s.timeout == 300
    assert s.timeout_session == 7200
    assert s.modules == "nsh"


def test_load_options_defaults(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)
    path = _write_yaml(
        tmp,
        "manifest.yaml",
        f"""\

        sessions:
          - name: s1
            confpath: "{confpath}"
            testpath: "{tmp}"
        """,
    )
    mc = ManifestConfig.load(path)
    assert mc.options.fail_fast is False
    assert mc.options.parallel is False


def test_resolve_session_timeout_overrides(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[
            SessionConfig(
                name="s1",
                confpath=confpath,
                testpath=tmp,
                loops=5,
                timeout=999,
                timeout_session=8888,
            )
        ],
    )

    conf = mc.resolve_session_config(mc.sessions[0])
    assert conf["config"]["loops"] == 5
    assert conf["config"]["timeout"] == 999
    assert conf["config"]["timeout_session"] == 8888


def test_resolve_no_overrides(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )

    conf = mc.resolve_session_config(mc.sessions[0])
    assert "build_env" not in conf.get("config", {})


def test_run_all_pass(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)
    testdir = os.path.join(tmp, "tests")
    os.makedirs(testdir)

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[
            SessionConfig(name="s1", confpath=confpath, testpath=testdir),
            SessionConfig(name="s2", confpath=confpath, testpath=testdir),
        ],
    )
    runner = _make_runner(mc)

    mock_log_mgr = MagicMock()
    mock_log_mgr.new_session_dir.return_value = tmp

    with (
        patch.object(runner, "_phase_build") as mock_build,
        patch.object(runner, "_phase_test") as mock_test,
        patch.object(runner, "_phase_report"),
        patch("ntfc.multi.LogManager", return_value=mock_log_mgr),
    ):
        mock_build.return_value = {"s1": {}, "s2": {}}
        mock_test.return_value = [
            SessionResult("s1", 0, os.path.join(tmp, "s1")),
            SessionResult("s2", 0, os.path.join(tmp, "s2")),
        ]
        assert runner.run() == 0


def test_run_session_fails(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )
    runner = _make_runner(mc)

    mock_log_mgr = MagicMock()
    mock_log_mgr.new_session_dir.return_value = tmp

    with (
        patch.object(runner, "_phase_build") as mock_build,
        patch.object(runner, "_phase_test") as mock_test,
        patch.object(runner, "_phase_report"),
        patch("ntfc.multi.LogManager", return_value=mock_log_mgr),
    ):
        mock_build.return_value = {"s1": {}}
        mock_test.return_value = [
            SessionResult("s1", 1, os.path.join(tmp, "s1")),
        ]
        assert runner.run() == 1


def test_run_build_fails(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )
    runner = _make_runner(mc)

    with (
        patch.object(runner, "_phase_build") as mock_build,
        patch.object(runner, "_phase_test") as mock_test,
    ):
        mock_build.return_value = None
        assert runner.run() == 1
        mock_test.assert_not_called()


def test_phase_build_dedup(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[
            SessionConfig(name="s1", confpath=confpath, testpath=tmp),
            SessionConfig(name="s2", confpath=confpath, testpath=tmp),
        ],
    )
    runner = _make_runner(mc)

    mock_builder = MagicMock()
    mock_builder.need_build.return_value = False

    with patch("ntfc.multi.NuttXBuilder", return_value=mock_builder):
        result = runner._phase_build()

    assert result is not None
    assert "s1" in result
    assert "s2" in result
    assert result["s1"] is result["s2"]


def test_phase_build_exception(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )
    runner = _make_runner(mc)

    mock_builder = MagicMock()
    mock_builder.need_build.return_value = True
    mock_builder.build_all.side_effect = RuntimeError("fail")

    with patch("ntfc.multi.NuttXBuilder", return_value=mock_builder):
        result = runner._phase_build()

    assert result is None


def test_phase_build_success_with_builder(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )
    runner = _make_runner(mc)

    new_conf = {"config": {"loops": 1}, "product": {"built": True}}
    mock_builder = MagicMock()
    mock_builder.need_build.return_value = True
    mock_builder.new_conf.return_value = new_conf

    with patch("ntfc.multi.NuttXBuilder", return_value=mock_builder):
        result = runner._phase_build()

    assert result is not None
    assert result["s1"]["product"]["built"] is True


def test_sequential_fail_fast(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(fail_fast=True),
        sessions=[
            SessionConfig(name="s1", confpath=confpath, testpath=tmp),
            SessionConfig(name="s2", confpath=confpath, testpath=tmp),
        ],
    )
    runner = _make_runner(mc)

    call_count = 0

    def mock_run_session(
        session: SessionConfig,
        conf: dict,  # type: ignore[type-arg]
        fail_event: object = None,
    ) -> SessionResult:
        nonlocal call_count
        call_count += 1
        return SessionResult(name=session.name, exit_code=1, result_dir=tmp)

    runner._run_session = mock_run_session  # type: ignore[assignment]

    results = runner._run_sequential({"s1": {}, "s2": {}})
    assert len(results) == 1
    assert results[0].name == "s1"
    assert call_count == 1


def test_sequential_no_fail_fast(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(fail_fast=False),
        sessions=[
            SessionConfig(name="s1", confpath=confpath, testpath=tmp),
            SessionConfig(name="s2", confpath=confpath, testpath=tmp),
        ],
    )
    runner = _make_runner(mc)

    def mock_run_session(
        session: SessionConfig,
        conf: dict,  # type: ignore[type-arg]
        fail_event: object = None,
    ) -> SessionResult:
        return SessionResult(name=session.name, exit_code=1, result_dir=tmp)

    runner._run_session = mock_run_session  # type: ignore[assignment]

    results = runner._run_sequential({"s1": {}, "s2": {}})
    assert len(results) == 2


def test_parallel_no_resources(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(parallel=True),
        sessions=[
            SessionConfig(name="s1", confpath=confpath, testpath=tmp),
            SessionConfig(name="s2", confpath=confpath, testpath=tmp),
        ],
    )
    runner = MultiSessionRunner(mc, rebuild=False)

    executed: list[str] = []
    lock = threading.Lock()

    def mock_run_session(
        session: SessionConfig,
        conf: dict,  # type: ignore[type-arg]
        fail_event: object = None,
    ) -> SessionResult:
        with lock:
            executed.append(session.name)
        return SessionResult(name=session.name, exit_code=0, result_dir=tmp)

    runner._run_session = mock_run_session  # type: ignore[assignment]

    results = runner._run_parallel({"s1": {}, "s2": {}})
    assert len(results) == 2
    assert {r.name for r in results} == {"s1", "s2"}


def test_parallel_resource_serialization(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(parallel=True),
        sessions=[
            SessionConfig(
                name="s1",
                confpath=confpath,
                testpath=tmp,
                resources=["vcan0"],
            ),
            SessionConfig(
                name="s2",
                confpath=confpath,
                testpath=tmp,
                resources=["vcan0"],
            ),
        ],
    )
    runner = MultiSessionRunner(mc, rebuild=False)

    concurrent_count = 0
    max_concurrent = 0
    count_lock = threading.Lock()

    def mock_run_session(
        session: SessionConfig,
        conf: dict,  # type: ignore[type-arg]
        fail_event: object = None,
    ) -> SessionResult:
        nonlocal concurrent_count, max_concurrent
        with count_lock:
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
        time.sleep(0.05)
        with count_lock:
            concurrent_count -= 1
        return SessionResult(name=session.name, exit_code=0, result_dir=tmp)

    runner._run_session = mock_run_session  # type: ignore[assignment]

    results = runner._run_parallel({"s1": {}, "s2": {}})
    assert len(results) == 2
    assert max_concurrent == 1


def test_parallel_fail_fast(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(fail_fast=True, parallel=True),
        sessions=[
            SessionConfig(
                name="s1",
                confpath=confpath,
                testpath=tmp,
                resources=["res"],
            ),
            SessionConfig(
                name="s2",
                confpath=confpath,
                testpath=tmp,
                resources=["res"],
            ),
        ],
    )
    runner = MultiSessionRunner(mc, rebuild=False)

    def mock_run_session(
        session: SessionConfig,
        conf: dict,  # type: ignore[type-arg]
        fail_event: object = None,
    ) -> SessionResult:
        code = 1 if session.name == "s1" else -1
        return SessionResult(name=session.name, exit_code=code, result_dir=tmp)

    runner._run_session = mock_run_session  # type: ignore[assignment]

    results = runner._run_parallel({"s1": {}, "s2": {}})
    failed = [r for r in results if r.exit_code != 0]
    assert len(failed) >= 1


def test_parallel_results_sorted(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(parallel=True),
        sessions=[
            SessionConfig(name="alpha", confpath=confpath, testpath=tmp),
            SessionConfig(name="beta", confpath=confpath, testpath=tmp),
            SessionConfig(name="gamma", confpath=confpath, testpath=tmp),
        ],
    )
    runner = MultiSessionRunner(mc, rebuild=False)

    def mock_run_session(
        session: SessionConfig,
        conf: dict,  # type: ignore[type-arg]
        fail_event: object = None,
    ) -> SessionResult:
        return SessionResult(name=session.name, exit_code=0, result_dir=tmp)

    runner._run_session = mock_run_session  # type: ignore[assignment]

    results = runner._run_parallel({"alpha": {}, "beta": {}, "gamma": {}})
    assert [r.name for r in results] == ["alpha", "beta", "gamma"]


def test_run_session_abort_on_fail_event(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(fail_fast=True),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )
    runner = MultiSessionRunner(mc, rebuild=False)

    fail_event = threading.Event()
    fail_event.set()

    result = runner._run_session(mc.sessions[0], {}, fail_event)
    assert result.exit_code == -1


def test_run_session_calls_mypytest(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[
            SessionConfig(
                name="s1",
                confpath=confpath,
                testpath=tmp,
                modules="nsh,shell",
            )
        ],
    )
    runner = MultiSessionRunner(mc, rebuild=False)
    runner._session_dir = tmp

    mock_pt = MagicMock()
    mock_pt.runner.return_value = 0
    mock_pt.result_dir = "/tmp/fake_result"

    with patch("ntfc.multi.MyPytest", return_value=mock_pt):
        result = runner._run_session(mc.sessions[0], {})

    assert result.exit_code == 0
    assert result.result_dir == "/tmp/fake_result"
    mock_pt.runner.assert_called_once()

    # Verify result_dir was passed to runner
    call_args = mock_pt.runner.call_args
    result_dict = call_args[0][1]
    assert result_dict["result_dir"] == os.path.join(tmp, "s1")


def test_run_session_sets_fail_event(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(fail_fast=True),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )
    runner = MultiSessionRunner(mc, rebuild=False)
    runner._session_dir = tmp

    fail_event = threading.Event()

    mock_pt = MagicMock()
    mock_pt.runner.return_value = 1
    mock_pt.result_dir = ""

    with patch("ntfc.multi.MyPytest", return_value=mock_pt):
        runner._run_session(mc.sessions[0], {}, fail_event)

    assert fail_event.is_set()


def test_phase_test_sequential(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(parallel=False),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )
    runner = MultiSessionRunner(mc, rebuild=False)

    called = []

    def mock_sequential(
        built_configs: dict,  # type: ignore[type-arg]
    ) -> list:  # type: ignore[type-arg]
        called.append("sequential")
        return [SessionResult("s1", 0, tmp)]

    runner._run_sequential = mock_sequential  # type: ignore[assignment]

    results = runner._phase_test({"s1": {}})

    assert called == ["sequential"]
    assert len(results) == 1


def test_phase_test_parallel(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(parallel=True),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )
    runner = MultiSessionRunner(mc, rebuild=False)

    called = []

    def mock_parallel(
        built_configs: dict,  # type: ignore[type-arg]
    ) -> list:  # type: ignore[type-arg]
        called.append("parallel")
        return [SessionResult("s1", 0, tmp)]

    runner._run_parallel = mock_parallel  # type: ignore[assignment]

    results = runner._phase_test({"s1": {}})

    assert called == ["parallel"]
    assert len(results) == 1


def test_phase_report(tmp_path):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )
    runner = MultiSessionRunner(mc, rebuild=False)
    runner._session_dir = tmp

    results = [SessionResult("s1", 0, tmp)]

    with (
        patch("ntfc.multi.Reporter") as mock_rep_cls,
        patch.object(
            MultiSessionRunner, "_merge_session_reports"
        ) as mock_merge,
    ):
        mock_reporter = MagicMock()
        mock_rep_cls.return_value = mock_reporter

        runner._phase_report(results)

    mock_merge.assert_called_once_with(tmp, results, mock_reporter)


def test_merge_two_sessions(tmp_path):
    tmp = str(tmp_path)
    master = os.path.join(tmp, "master")
    os.makedirs(master)

    s1_dir = os.path.join(master, "s1")
    os.makedirs(s1_dir)
    _make_junit_xml(os.path.join(s1_dir, "report.xml"), "module_a", 2)

    s2_dir = os.path.join(master, "s2")
    os.makedirs(s2_dir)
    _make_junit_xml(os.path.join(s2_dir, "report.xml"), "module_b", 3)

    results = [
        SessionResult("s1", 0, s1_dir),
        SessionResult("s2", 0, s2_dir),
    ]

    reporter = MagicMock()
    MultiSessionRunner._merge_session_reports(master, results, reporter)

    merged_path = os.path.join(master, "report.xml")
    assert os.path.exists(merged_path)

    tree = ElementTree.parse(merged_path)
    root = tree.getroot()
    suites = root.findall("testsuite")
    assert len(suites) == 2

    names = {s.get("name") for s in suites}
    assert "s1::module_a" in names
    assert "s2::module_b" in names

    for tc in root.findall(".//testcase"):
        assert "::" in tc.get("classname", "")

    reporter.generate_result_summary.assert_called_once_with(master)


def test_merge_missing_xml(tmp_path):
    tmp = str(tmp_path)
    master = os.path.join(tmp, "master")
    os.makedirs(master)

    results = [
        SessionResult("s1", 0, os.path.join(master, "s1")),
    ]

    reporter = MagicMock()
    MultiSessionRunner._merge_session_reports(master, results, reporter)

    assert os.path.exists(os.path.join(master, "report.xml"))


def test_merge_invalid_xml(tmp_path):
    tmp = str(tmp_path)
    master = os.path.join(tmp, "master")
    s1_dir = os.path.join(master, "s1")
    os.makedirs(s1_dir)

    with open(os.path.join(s1_dir, "report.xml"), "w") as f:
        f.write("not xml at all <><><>")

    results = [SessionResult("s1", 0, s1_dir)]

    reporter = MagicMock()
    MultiSessionRunner._merge_session_reports(master, results, reporter)

    assert os.path.exists(os.path.join(master, "report.xml"))


def test_merge_with_failure_elements(tmp_path):
    tmp = str(tmp_path)
    master = os.path.join(tmp, "master")
    s1_dir = os.path.join(master, "s1")
    os.makedirs(s1_dir)

    root = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(root, "testsuite")
    suite.set("name", "mod")
    suite.set("tests", "1")
    suite.set("failures", "1")
    suite.set("errors", "0")
    suite.set("skipped", "0")
    suite.set("time", "1.0")

    tc = ElementTree.SubElement(suite, "testcase")
    tc.set("name", "test_fail")
    tc.set("classname", "mod::Test")
    tc.set("time", "0.5")
    fail = ElementTree.SubElement(tc, "failure")
    fail.set("message", "assertion error")
    fail.text = "traceback here"

    tree = ElementTree.ElementTree(root)
    tree.write(os.path.join(s1_dir, "report.xml"))

    results = [SessionResult("s1", 1, s1_dir)]
    reporter = MagicMock()
    MultiSessionRunner._merge_session_reports(master, results, reporter)

    merged = ElementTree.parse(os.path.join(master, "report.xml"))
    failures = merged.findall(".//failure")
    assert len(failures) == 1
    assert failures[0].get("message") == "assertion error"
    assert failures[0].text == "traceback here"


def test_merge_child_without_text(tmp_path):
    tmp = str(tmp_path)
    master = os.path.join(tmp, "master")
    s1_dir = os.path.join(master, "s1")
    os.makedirs(s1_dir)

    root = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(root, "testsuite")
    suite.set("name", "mod")
    suite.set("tests", "1")
    suite.set("failures", "0")
    suite.set("errors", "0")
    suite.set("skipped", "1")
    suite.set("time", "0.0")

    tc = ElementTree.SubElement(suite, "testcase")
    tc.set("name", "test_skip")
    tc.set("classname", "mod::Test")
    tc.set("time", "0.0")
    skip = ElementTree.SubElement(tc, "skipped")
    skip.set("message", "not applicable")

    tree = ElementTree.ElementTree(root)
    tree.write(os.path.join(s1_dir, "report.xml"))

    results = [SessionResult("s1", 0, s1_dir)]
    reporter = MagicMock()
    MultiSessionRunner._merge_session_reports(master, results, reporter)

    merged = ElementTree.parse(os.path.join(master, "report.xml"))
    skipped = merged.findall(".//skipped")
    assert len(skipped) == 1
    assert skipped[0].get("message") == "not applicable"
    assert skipped[0].text is None


def test_build_key_same_config():
    mc = ManifestConfig(options=MultiOptions(), sessions=[])
    runner = MultiSessionRunner(mc, rebuild=False)

    conf = {
        "config": {"build_env": {"CC": "gcc"}},
        "product": {"cores": {"core0": {"defconfig": "path/a"}}},
    }
    assert runner._build_key(conf) == runner._build_key(conf)


def test_build_key_different_defconfig():
    mc = ManifestConfig(options=MultiOptions(), sessions=[])
    runner = MultiSessionRunner(mc, rebuild=False)

    conf1 = {
        "config": {},
        "product": {"cores": {"core0": {"defconfig": "path/a"}}},
    }
    conf2 = {
        "config": {},
        "product": {"cores": {"core0": {"defconfig": "path/b"}}},
    }
    assert runner._build_key(conf1) != runner._build_key(conf2)


def test_build_key_no_defconfig():
    mc = ManifestConfig(options=MultiOptions(), sessions=[])
    runner = MultiSessionRunner(mc, rebuild=False)

    conf = {"config": {}, "product": {"cores": {"core0": {}}}}
    key = runner._build_key(conf)
    assert isinstance(key, frozenset)


def test_build_key_kv_affects_key():
    mc = ManifestConfig(options=MultiOptions(), sessions=[])
    runner = MultiSessionRunner(mc, rebuild=False)

    conf1 = {
        "config": {"kv": {"K": "1"}},
        "product": {"cores": {"core0": {"defconfig": "p"}}},
    }
    conf2 = {
        "config": {"kv": {"K": "2"}},
        "product": {"cores": {"core0": {"defconfig": "p"}}},
    }
    assert runner._build_key(conf1) != runner._build_key(conf2)


def test_print_summary_all_states(tmp_path, capsys):
    tmp = str(tmp_path)
    confpath = _write_config_yaml(tmp)

    s1_dir = os.path.join(tmp, "s1")
    s2_dir = os.path.join(tmp, "s2")
    _write_report_xml(
        s1_dir,
        '<testsuites><testsuite tests="5" failures="0"'
        ' skipped="0" errors="0" time="10.5"/></testsuites>',
    )
    _write_report_xml(
        s2_dir,
        '<testsuites><testsuite tests="3" failures="2"'
        ' skipped="1" errors="0" time="5.0"/></testsuites>',
    )

    mc = ManifestConfig(
        options=MultiOptions(),
        sessions=[SessionConfig(name="s1", confpath=confpath, testpath=tmp)],
    )
    runner = MultiSessionRunner(mc, rebuild=False)

    results = [
        SessionResult("s1", 0, s1_dir),
        SessionResult("s2", 1, s2_dir),
        SessionResult("s3", -1, ""),
    ]
    runner._print_summary(results)

    out = capsys.readouterr().out
    assert "PASS" in out
    assert "FAIL" in out
    assert "SKIP" in out
    assert "sessions:3 passed:1 failed:1 skipped:1" in out
    assert "Total" in out


def test_parse_session_counts_no_xml():
    assert MultiSessionRunner._parse_session_counts("/nonexistent") == (
        0,
        0,
        0,
        0,
        0.0,
    )


def test_parse_session_counts_from_report_subdir(tmp_path):
    tmp = str(tmp_path)
    report_dir = os.path.join(tmp, "report")
    os.makedirs(report_dir)
    with open(os.path.join(report_dir, "001_shell.xml"), "w") as f:
        f.write(
            '<testsuites><testsuite tests="4" failures="1"'
            ' skipped="0" errors="0" time="2.0"/></testsuites>'
        )
    with open(os.path.join(report_dir, "002_can.xml"), "w") as f:
        f.write(
            '<testsuites><testsuite tests="3" failures="0"'
            ' skipped="1" errors="0" time="1.5"/></testsuites>'
        )
    p, f, s, e, t = MultiSessionRunner._parse_session_counts(tmp)
    assert p == 5
    assert f == 1
    assert s == 1
    assert e == 0
    assert t == 3.5


def test_parse_session_counts_bad_xml(tmp_path):
    tmp = str(tmp_path)
    _write_report_xml(tmp, "<<<not xml>>>")
    assert MultiSessionRunner._parse_session_counts(tmp) == (0, 0, 0, 0, 0.0)


def test_parse_session_counts_bad_xml_in_report_dir(tmp_path):
    tmp = str(tmp_path)
    report_dir = os.path.join(tmp, "report")
    os.makedirs(report_dir)
    with open(os.path.join(report_dir, "001_bad.xml"), "w") as f:
        f.write("<<<not xml>>>")
    assert MultiSessionRunner._parse_session_counts(tmp) == (0, 0, 0, 0, 0.0)
