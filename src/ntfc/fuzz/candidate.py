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

"""Build, run, and classify one fuzz candidate.

A candidate is a base config plus a set of ``CONFIG_*`` toggles. The build path
goes through :meth:`ntfc.builder.NuttXBuilder.build_candidate`; the run path
boots the built image through NTFC's device layer (sim / QEMU / serial) and
classifies the outcome. ``classify_run`` is pure and unit-tested; the build/run
glue shells out and drives hardware, so it is integration-only.
"""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, Optional, Tuple

from ntfc.fuzz.mocks import append_mock_defines, missing_board_constants

if TYPE_CHECKING:
    from ntfc.builder import NuttXBuilder
    from ntfc.fuzz.profiles import ArchProfile

PASS = "pass"
PASS_MOCKED = "pass-mocked"
BUILD_FAIL = "build-fail"
TEST_FAIL = "test-fail"
CRASH = "crash"
TIMEOUT = "timeout"
STATUSES = (PASS, PASS_MOCKED, BUILD_FAIL, TEST_FAIL, CRASH, TIMEOUT)


@dataclass
class Outcome:
    """The result of evaluating one candidate configuration."""

    configs: FrozenSet[str]
    status: str
    detail: str = ""
    log_path: Optional[str] = None
    elf_path: Optional[str] = None
    mocks: Optional[Dict[str, str]] = None

    @property
    def ok(self) -> bool:
        """Whether the candidate passed (natively or after mocking)."""
        return self.status in (PASS, PASS_MOCKED)


def classify_run(
    output: str, rc: int, timed_out: bool, patterns: Dict[str, Any]
) -> Tuple[str, str]:
    """Map captured run output + exit code to a ``(status, detail)`` pair."""
    if timed_out:
        return TIMEOUT, "no completion within timeout (hang)"
    m = re.search(patterns["ostest_exit"], output)
    if m:
        code = int(m.group(1))
        if code == 0:
            return PASS, ""
        return TEST_FAIL, f"ostest status {code}"
    if re.search(patterns["crash"], output, re.IGNORECASE):
        return CRASH, "assertion/panic in output"
    if rc == -11:
        return CRASH, "segfault (SIGSEGV)"
    return CRASH, f"did not finish ostest (exit {rc})"


def extract_errors(
    log: str, patterns: Dict[str, Any], max_lines: int = 20
) -> str:
    """Pull the most relevant error lines out of a build/run log.

    Lines matching the ``build_error`` patterns are returned; if none match,
    the tail of the log is used as a fallback.
    """
    rx = re.compile("|".join(patterns["build_error"]), re.IGNORECASE)
    hits = [ln.rstrip() for ln in log.splitlines() if rx.search(ln)]
    if not hits:
        hits = [ln.rstrip() for ln in log.splitlines() if ln.strip()]
        hits = hits[-max_lines:]
    return "\n".join(hits[:max_lines])


def _config_header(build_dir: str) -> Path:  # pragma: no cover
    """Path to the build's generated, force-included nuttx/config.h."""
    return Path(build_dir) / "include" / "nuttx" / "config.h"


def _save_log(  # pragma: no cover
    log_dir: str, kind: str, configs: FrozenSet[str], output: str
) -> str:
    """Write a build/run log to a file and return its path."""
    os.makedirs(log_dir, exist_ok=True)
    tag = "baseline" if not configs else "_".join(sorted(configs))
    path = os.path.join(log_dir, f"{kind}-{tag}.log")
    with open(path, "w", encoding="utf-8") as f:
        f.write(output)
    return path


def build_one(  # pragma: no cover  # noqa: C901
    builder: "NuttXBuilder",
    board_config: str,
    configs: FrozenSet[str],
    build_dir: str,
    *,
    mock: bool = False,
    profile: Optional["ArchProfile"] = None,
    jobs: Optional[int] = None,
    mock_max_iters: int = 8,
    cleanup: bool = True,
    log_dir: Optional[str] = None,
    patterns: Optional[Dict[str, Any]] = None,
) -> Outcome:
    """Build one candidate; classify pass / pass-mocked / build-fail.

    With ``mock`` set, when a build fails the missing board-supplied constants
    are synthesised into the build's ``config.h`` and the build retried, up to
    ``mock_max_iters`` rounds, so the arch build path can be validated without
    a real board wiring. ``cleanup`` removes the build dir when done; the
    ostest/mem modes pass ``cleanup=False`` because they use the built ELF. On
    a build failure the full compiler log is written to ``log_dir`` and the
    first error line becomes the outcome ``detail``.
    """
    kv = {c: True for c in configs}

    def fail(res: Any, injected: Optional[Dict[str, str]] = None) -> Outcome:
        detail = "build failed"
        if patterns is not None:
            errs = extract_errors(res.log, patterns)
            if errs:
                detail = errs.splitlines()[0][:200]
        log_path = None
        if log_dir is not None:
            log_path = _save_log(log_dir, "build", configs, res.log)
        return Outcome(
            configs,
            BUILD_FAIL,
            detail,
            log_path=log_path,
            elf_path=res.elf_path,
            mocks=injected or None,
        )

    try:
        res = builder.build_candidate(board_config, kv, build_dir, jobs=jobs)
        if res.ok:
            return Outcome(configs, PASS, elf_path=res.elf_path)
        if not mock or profile is None:
            return fail(res)

        injected: Dict[str, str] = {}
        header = _config_header(build_dir)
        for _ in range(mock_max_iters):
            new = missing_board_constants(res.log, profile, injected)
            if not new:
                break
            injected.update(new)
            append_mock_defines(header, new)
            # configure=False: a reconfigure would regenerate config.h and
            # discard the mocks appended above
            res = builder.build_candidate(
                board_config, kv, build_dir, jobs=jobs, configure=False
            )
            if res.ok:
                return Outcome(
                    configs, PASS_MOCKED, elf_path=res.elf_path, mocks=injected
                )
        return fail(res, injected)
    finally:
        if cleanup:
            shutil.rmtree(build_dir, ignore_errors=True)


def run_one(  # pragma: no cover
    core_conf: Dict[str, Any],
    configs: FrozenSet[str],
    patterns: Dict[str, Any],
    timeout: float,
    log_dir: Optional[str] = None,
) -> Outcome:
    """Boot a built candidate to NSH, run ``ostest``, and classify it.

    The base config is an NSH target (sim / QEMU / serial). The device is
    booted through the device layer, the ``ostest`` builtin is run, and it is
    read until the NSH prompt returns (or the timeout). The
    ``ostest_main: Exiting with status N`` line is authoritative (0 -> pass,
    else test-fail); otherwise a crash signature -> crash, a hang -> timeout,
    refined by the device's busy-loop / not-alive state. The console output of
    any non-pass run is saved to ``log_dir``.

    ostest under the simulator runs the full suite and is not real-time, so it
    can take minutes; give ``timeout`` plenty of headroom.
    """
    from ntfc.coreconfig import CoreConfig
    from ntfc.device.getdev import get_device

    dev = get_device(CoreConfig(core_conf))
    try:
        dev.start()
        if not dev._wait_for_boot(int(timeout)):
            return Outcome(configs, TIMEOUT, "device did not boot")
        res = dev.send_cmd_read_until_pattern(
            b"ostest", dev.prompt, int(timeout)
        )
        out = res.output
        timed_out = res.status.name == "TIMEOUT"
        status, detail = classify_run(out, 0, timed_out, patterns)
        if status == CRASH:
            if dev.busyloop:
                status, detail = TIMEOUT, "device busy-loop"
            elif dev.notalive:
                detail = "device not alive; " + detail
        log_path = None
        if log_dir is not None and status != PASS:
            log_path = _save_log(log_dir, "run", configs, out)
        return Outcome(configs, status, detail, log_path=log_path)
    finally:
        dev.stop()
