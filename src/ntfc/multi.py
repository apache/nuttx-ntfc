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

"""Multi-session test integrator for NTFC."""

import glob
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple
from xml.etree import ElementTree

import yaml  # type: ignore
from prettytable import PrettyTable

from ntfc.builder import NuttXBuilder
from ntfc.log.logger import logger
from ntfc.log.manager import LogManager
from ntfc.log.report import Reporter
from ntfc.pytest.mypytest import MyPytest

###############################################################################
# Dataclass: SessionConfig
###############################################################################


@dataclass
class SessionConfig:
    """Configuration for a single test session."""

    name: str
    confpath: str
    testpath: str
    resources: List[str] = field(default_factory=list)
    exitonfail: Optional[bool] = None
    loops: Optional[int] = None
    timeout: Optional[int] = None
    timeout_session: Optional[int] = None
    modules: Optional[str] = None


###############################################################################
# Dataclass: MultiOptions
###############################################################################


@dataclass
class MultiOptions:
    """Global options for multi-session execution."""

    fail_fast: bool = False
    parallel: bool = False


###############################################################################
# Dataclass: SessionResult
###############################################################################


@dataclass
class SessionResult:
    """Result of a single test session execution."""

    name: str
    exit_code: int
    result_dir: str


###############################################################################
# Class: ManifestConfig
###############################################################################


class ManifestConfig:
    """Parse and validate a multi-session manifest YAML file."""

    def __init__(
        self,
        options: "MultiOptions",
        sessions: List["SessionConfig"],
    ) -> None:
        """Initialize ManifestConfig.

        :param options: Multi-session execution options.
        :param sessions: Ordered list of session configurations.
        """
        self.options = options
        self.sessions = sessions

    @classmethod
    def load(cls, path: str) -> "ManifestConfig":
        """Load and validate manifest from YAML file.

        :param path: Path to the manifest YAML file.
        :return: Validated ManifestConfig instance.
        :raises ValueError: If the manifest is invalid.
        :raises FileNotFoundError: If the manifest file does not exist.
        """
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("manifest must be a YAML mapping")

        options = cls._parse_options(data.get("options", {}))
        sessions = cls._parse_sessions(data.get("sessions", []))

        return cls(options, sessions)

    @staticmethod
    def _parse_options(raw_options: Any) -> "MultiOptions":
        """Parse and validate the options section.

        :param raw_options: Raw options from YAML.
        :return: Validated MultiOptions instance.
        """
        if not isinstance(raw_options, dict):
            raise ValueError("'options' must be a mapping")
        return MultiOptions(
            fail_fast=bool(raw_options.get("fail_fast", False)),
            parallel=bool(raw_options.get("parallel", False)),
        )

    @staticmethod
    def _parse_session(idx: int, raw: Any, names: set[str]) -> "SessionConfig":
        """Parse and validate a single session entry.

        :param idx: Index of the session in the list.
        :param raw: Raw session dict from YAML.
        :param names: Set of already-seen session names.
        :return: Validated SessionConfig instance.
        """
        if not isinstance(raw, dict):
            raise ValueError(f"session {idx} must be a mapping")
        name = raw.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(
                f"session {idx}: 'name' is required " f"and must be a string"
            )
        if name in names:
            raise ValueError(f"duplicate session name: '{name}'")
        names.add(name)

        confpath = raw.get("confpath")
        if not confpath or not isinstance(confpath, str):
            raise ValueError(f"session '{name}': 'confpath' is required")

        testpath = raw.get("testpath")
        if not testpath or not isinstance(testpath, str):
            raise ValueError(f"session '{name}': 'testpath' is required")

        resources = raw.get("resources", [])
        if not isinstance(resources, list):
            raise ValueError(f"session '{name}': 'resources' must be a list")

        return SessionConfig(
            name=name,
            confpath=confpath,
            testpath=testpath,
            resources=[str(r) for r in resources],
            exitonfail=raw.get("exitonfail"),
            loops=raw.get("loops"),
            timeout=raw.get("timeout"),
            timeout_session=raw.get("timeout_session"),
            modules=raw.get("modules"),
        )

    @classmethod
    def _parse_sessions(cls, raw_sessions: Any) -> List["SessionConfig"]:
        """Parse and validate the sessions list.

        :param raw_sessions: Raw sessions list from YAML.
        :return: List of validated SessionConfig instances.
        """
        if not isinstance(raw_sessions, list) or not raw_sessions:
            raise ValueError("'sessions' must be a non-empty list")

        sessions: List[SessionConfig] = []
        names: set[str] = set()
        for idx, raw in enumerate(raw_sessions):
            sessions.append(cls._parse_session(idx, raw, names))

        return sessions

    def resolve_session_config(
        self, session: "SessionConfig"
    ) -> Dict[str, Any]:
        """Load session YAML config and apply per-session overrides.

        :param session: Session configuration to resolve.
        :return: Configuration dictionary.
        """
        with open(session.confpath, encoding="utf-8") as f:
            conf: Dict[str, Any] = yaml.safe_load(f) or {}

        # apply per-session overrides
        cfg = conf.setdefault("config", {})
        if session.loops is not None:
            cfg["loops"] = session.loops
        if session.timeout is not None:
            cfg["timeout"] = session.timeout
        if session.timeout_session is not None:
            cfg["timeout_session"] = session.timeout_session

        return conf


###############################################################################
# Class: MultiSessionRunner
###############################################################################


class MultiSessionRunner:
    """Orchestrate multi-session build, test, and report merging."""

    def __init__(
        self,
        manifest: "ManifestConfig",
        rebuild: bool = True,
        verbose: bool = False,
        debug: bool = False,
        logcfg: Optional[str] = None,
    ) -> None:
        """Initialize MultiSessionRunner.

        :param manifest: Parsed manifest configuration.
        :param rebuild: Force rebuild of all configurations.
        :param verbose: Enable verbose output.
        :param debug: Enable debug output.
        :param logcfg: Path to log configuration file.
        """
        self._manifest = manifest
        self._rebuild = rebuild
        self._verbose = verbose
        self._debug = debug
        self._logcfg = logcfg

    def run(self) -> int:
        """Execute the full multi-session pipeline.

        :return: 0 if all sessions passed, 1 otherwise.
        """
        # Phase 1: Build all configurations
        built_configs = self._phase_build()
        if built_configs is None:
            return 1

        # Create shared session directory for all sessions
        log_manager = LogManager(self._logcfg)
        log_manager.cleanup()
        self._session_dir = log_manager.new_session_dir()

        # Phase 2: Run all test sessions
        results = self._phase_test(built_configs)

        # Phase 3: Merge reports into the shared session directory
        self._phase_report(results)

        # Print final summary
        self._print_summary(results)

        # Aggregate exit codes
        for r in results:
            if r.exit_code != 0:
                return 1
        return 0

    @staticmethod
    def _parse_session_counts(
        result_dir: str,
    ) -> Tuple[int, int, int, int, float]:
        """Parse test counts from a session's report XML files.

        The Reporter splits the original ``report.xml`` into per-module
        files under ``<result_dir>/report/`` and deletes the original.
        This method reads those per-module files.  Falls back to
        ``report.xml`` if the split directory does not exist.

        :param result_dir: Path to session result directory.
        :return: Tuple of (passes, failures, skipped, errors, time).
        """
        # Reporter splits report.xml into per-module files here
        report_dir = os.path.join(result_dir, "report")

        xml_files: List[str] = []
        if os.path.isdir(report_dir):
            xml_files = sorted(glob.glob(os.path.join(report_dir, "*.xml")))

        # fallback to unsplit report.xml
        if not xml_files:
            single = os.path.join(result_dir, "report.xml")
            if os.path.exists(single):
                xml_files = [single]

        if not xml_files:
            return 0, 0, 0, 0, 0.0

        passes = 0
        failures = 0
        skipped_count = 0
        errors = 0
        total_time = 0.0

        for xml_path in xml_files:
            try:
                root = ElementTree.parse(xml_path).getroot()
            except ElementTree.ParseError:
                continue

            for ts in root.iter("testsuite"):
                total = int(ts.attrib.get("tests", 0))
                f = int(ts.attrib.get("failures", 0))
                s = int(ts.attrib.get("skipped", 0))
                e = int(ts.attrib.get("errors", 0))
                t = float(ts.attrib.get("time", 0))
                passes += max(total - f - s, 0)
                failures += f
                skipped_count += s
                errors += e
                total_time += t

        return passes, failures, skipped_count, errors, total_time

    def _print_summary(self, results: List["SessionResult"]) -> None:
        """Print a summary table of all session results.

        :param results: List of session results.
        """
        table = PrettyTable()
        table.field_names = [
            "Session",
            "Result",
            "Pass",
            "Fail",
            "Skip",
            "Error",
            "Time",
        ]
        table.align["Session"] = "l"

        sess_passed = 0
        sess_failed = 0
        sess_skipped = 0
        total_pass = 0
        total_fail = 0
        total_skip = 0
        total_error = 0
        total_time = 0.0

        for r in results:
            if r.exit_code == 0:
                status = "PASS"
                sess_passed += 1
            elif r.exit_code == -1:
                status = "SKIP"
                sess_skipped += 1
            else:
                status = "FAIL"
                sess_failed += 1

            p, f, s, e, t = self._parse_session_counts(r.result_dir)
            total_pass += p
            total_fail += f
            total_skip += s
            total_error += e
            total_time += t
            table.add_row([r.name, status, p, f, s, e, f"{t:.2f}"])

        table.add_row(
            [
                "Total",
                "",
                total_pass,
                total_fail,
                total_skip,
                total_error,
                f"{total_time:.2f}",
            ]
        )

        total = len(results)
        summary = (
            f"[MULTI_SUMMARY] sessions:{total} "
            f"passed:{sess_passed} failed:{sess_failed} "
            f"skipped:{sess_skipped}"
        )
        print(f"\n\n{table}\n{summary}")

    def _build_key(self, conf: Dict[str, Any]) -> FrozenSet[Tuple[str, str]]:
        """Compute deduplication key from config.

        :param conf: Configuration dictionary.
        :return: Frozenset of identifying tuples.
        """
        items: list[Tuple[str, str]] = []

        # collect all defconfigs and build_env from all products/cores
        for key in conf:
            if "product" not in key:
                continue
            cores = conf[key].get("cores", {})
            for core_name in sorted(cores):
                core = cores[core_name]
                defconfig = core.get("defconfig", "")
                if defconfig:
                    items.append((f"{key}.{core_name}.defconfig", defconfig))

        # include global build_env
        build_env = conf.get("config", {}).get("build_env", {})
        for k, v in sorted(build_env.items()):
            items.append((f"build_env.{k}", str(v)))

        # include kv overrides
        kv = conf.get("config", {}).get("kv", {})
        for k, v in sorted(kv.items()):
            items.append((f"kv.{k}", str(v)))

        return frozenset(items)

    def _phase_build(
        self,
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """Build all unique configurations.

        :return: Mapping of session name to built config, or None
            on build failure.
        """
        logger.info("[Multi] Phase 1: Building all configurations")

        built_configs: Dict[str, Dict[str, Any]] = {}
        build_cache: Dict[FrozenSet[Tuple[str, str]], Dict[str, Any]] = {}

        for session in self._manifest.sessions:
            conf = self._manifest.resolve_session_config(session)
            bkey = self._build_key(conf)

            if bkey in build_cache:
                logger.info(
                    f"[Multi] Reusing build for session " f"'{session.name}'"
                )
                built_configs[session.name] = build_cache[bkey]
                continue

            # set loops default
            conf.setdefault("config", {}).setdefault("loops", 1)

            builder = NuttXBuilder(conf, self._rebuild)
            if builder.need_build():
                try:
                    builder.build_all()
                except Exception as e:
                    logger.error(
                        f"[Multi] Build failed for session "
                        f"'{session.name}': {e}"
                    )
                    return None
                conf = builder.new_conf()

            build_cache[bkey] = conf
            built_configs[session.name] = conf

        logger.info(
            f"[Multi] All {len(self._manifest.sessions)} "
            f"configurations built successfully"
        )
        return built_configs

    def _phase_test(
        self, built_configs: Dict[str, Dict[str, Any]]
    ) -> List["SessionResult"]:
        """Run test sessions with resource-aware scheduling.

        :param built_configs: Mapping of session name to config.
        :return: List of session results.
        """
        logger.info("[Multi] Phase 2: Running test sessions")

        if self._manifest.options.parallel:
            return self._run_parallel(built_configs)
        return self._run_sequential(built_configs)

    def _run_session(
        self,
        session: "SessionConfig",
        conf: Dict[str, Any],
        fail_event: Optional[threading.Event] = None,
    ) -> "SessionResult":
        """Run a single test session.

        :param session: Session configuration.
        :param conf: Resolved and built configuration dict.
        :param fail_event: Optional event to check for early abort.
        :return: Session result.
        """
        # check fail_fast abort
        if fail_event and fail_event.is_set():
            return SessionResult(
                name=session.name, exit_code=-1, result_dir=""
            )

        exitonfail = session.exitonfail or False
        modules = None
        if session.modules:
            modules = session.modules.replace(",", " ").split()

        pt = MyPytest(conf, exitonfail, self._verbose, modules=modules)

        logger.info(f"[Multi] Running session '{session.name}'")
        session_result_dir = os.path.join(self._session_dir, session.name)
        result: Dict[str, Any] = {
            "logcfg": self._logcfg,
            "result_dir": session_result_dir,
        }
        exit_code = pt.runner(session.testpath, result)

        # read result_dir from the instance, not global pytest module
        result_dir: str = pt.result_dir

        if fail_event and exit_code != 0 and self._manifest.options.fail_fast:
            fail_event.set()

        return SessionResult(
            name=session.name,
            exit_code=int(exit_code),
            result_dir=result_dir,
        )

    def _run_sequential(
        self, built_configs: Dict[str, Dict[str, Any]]
    ) -> List["SessionResult"]:
        """Run all sessions sequentially.

        :param built_configs: Mapping of session name to config.
        :return: List of session results.
        """
        results: List[SessionResult] = []
        for session in self._manifest.sessions:
            conf = built_configs[session.name]
            sr = self._run_session(session, conf)
            results.append(sr)

            if self._manifest.options.fail_fast and sr.exit_code != 0:
                logger.info(
                    f"[Multi] fail_fast: stopping after "
                    f"session '{session.name}'"
                )
                break

        return results

    def _run_parallel(
        self, built_configs: Dict[str, Dict[str, Any]]
    ) -> List["SessionResult"]:
        """Run sessions in parallel with resource-aware scheduling.

        Sessions with overlapping resources are serialized via locks.
        Sessions with no resource conflicts run concurrently.

        :param built_configs: Mapping of session name to config.
        :return: List of session results.
        """
        # create one lock per unique resource
        resource_locks: Dict[str, threading.Lock] = {}
        for session in self._manifest.sessions:
            for res in session.resources:
                if res not in resource_locks:
                    resource_locks[res] = threading.Lock()

        fail_event = threading.Event()
        results: List[SessionResult] = []
        results_lock = threading.Lock()

        def _worker(session: "SessionConfig") -> "SessionResult":
            # acquire all resource locks for this session
            locks = sorted(
                set(
                    resource_locks[r]
                    for r in session.resources
                    if r in resource_locks
                ),
                key=id,
            )
            for lock in locks:
                lock.acquire()
            try:
                conf = built_configs[session.name]
                return self._run_session(session, conf, fail_event)
            finally:
                for lock in locks:
                    lock.release()

        max_workers = max(1, len(self._manifest.sessions))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_worker, s): s for s in self._manifest.sessions
            }
            for future in as_completed(futures):
                sr = future.result()
                with results_lock:
                    results.append(sr)

        # sort results by original session order
        order = {s.name: i for i, s in enumerate(self._manifest.sessions)}
        results.sort(key=lambda r: order.get(r.name, 0))

        return results

    def _phase_report(self, results: List["SessionResult"]) -> None:
        """Merge sub-session reports into a unified report.

        :param results: List of session results from test phase.
        """
        logger.info("[Multi] Phase 3: Merging reports")

        reporter = Reporter()
        self._merge_session_reports(self._session_dir, results, reporter)

    @staticmethod
    def _copy_testcase(
        parent: ElementTree.Element,
        tc: ElementTree.Element,
        session_name: str,
    ) -> None:
        """Copy a testcase element with session-namespaced classname.

        :param parent: Parent testsuite element.
        :param tc: Source testcase element.
        :param session_name: Session name for namespacing.
        """
        new_tc = ElementTree.SubElement(parent, "testcase")
        for attr, val in tc.attrib.items():
            new_tc.set(attr, val)
        orig_cn = tc.get("classname", "")
        new_tc.set("classname", f"{session_name}::{orig_cn}")

        for child in tc:
            new_child = ElementTree.SubElement(new_tc, child.tag)
            for attr, val in child.attrib.items():
                new_child.set(attr, val)
            if child.text:
                new_child.text = child.text

    @classmethod
    def _merge_one_session(
        cls,
        root: ElementTree.Element,
        sr: "SessionResult",
    ) -> None:
        """Merge one session's report.xml into the root element.

        :param root: Root testsuites element to append to.
        :param sr: Session result with result_dir path.
        """
        xml_path = os.path.join(sr.result_dir, "report.xml")
        if not os.path.exists(xml_path):
            return

        try:
            tree = ElementTree.parse(xml_path)
        except ElementTree.ParseError:
            logger.warning(f"[Multi] Failed to parse {xml_path}")
            return

        src_root = tree.getroot()
        for testsuite in src_root.findall(".//testsuite"):
            new_suite = ElementTree.SubElement(root, "testsuite")
            for attr, val in testsuite.attrib.items():
                new_suite.set(attr, val)
            orig_name = testsuite.get("name", "")
            new_suite.set("name", f"{sr.name}::{orig_name}")

            for tc in testsuite.findall("testcase"):
                cls._copy_testcase(new_suite, tc, sr.name)

    @classmethod
    def _merge_session_reports(
        cls,
        master_dir: str,
        results: List["SessionResult"],
        reporter: "Reporter",
    ) -> None:
        """Merge sub-session JUnit XML reports into unified report.

        :param master_dir: Master session directory.
        :param results: List of session results.
        :param reporter: Reporter instance for summary generation.
        """
        root = ElementTree.Element("testsuites")

        for sr in results:
            cls._merge_one_session(root, sr)

        # write merged report
        merged_path = os.path.join(master_dir, "report.xml")
        merged_tree = ElementTree.ElementTree(root)
        merged_tree.write(merged_path)

        # generate unified summary using existing reporter
        reporter.generate_result_summary(master_dir)
