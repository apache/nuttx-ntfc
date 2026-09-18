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

"""Fuzz engine: turn a campaign into build/run/size candidates and a report.

The three feature modes (``build``, ``ostest``, ``mem``) share the same shape:
resolve the fuzz surface, generate candidate subsets, evaluate each through
NTFC's builder / device layer, and collect a ``FuzzReport``. The build/run/size
steps are injectable so the orchestration is unit-tested with fakes; the
defaults are the real integration functions.
"""

import itertools
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path  # noqa: TC003
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Sequence

from ntfc.builder import NuttXBuilder
from ntfc.fuzz import candidate, dataload, discover, memsize
from ntfc.fuzz.campaign import (
    CampaignError,
    FuzzConfig,
    board_config_of,
    build_target_conf,
)
from ntfc.fuzz.candidate import (
    BUILD_FAIL,
    CRASH,
    TEST_FAIL,
    TIMEOUT,
    Outcome,
)
from ntfc.fuzz.features import Feature, parse_features
from ntfc.fuzz.profiles import build_selector
from ntfc.fuzz.report import FuzzReport
from ntfc.fuzz.strategy import (
    ddmin,
    random_subsets,
    single_subsets,
    systematic_subsets,
)
from ntfc.log.logger import logger

_RUNTIME_FAILS = (CRASH, TEST_FAIL, TIMEOUT)

# Progress callback: called with a human-readable step message. Defaults to a
# no-op; the CLI passes a printer so users see live progress during long runs.
Progress = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


def _label(configs: FrozenSet[str]) -> str:
    return "baseline" if not configs else "{" + ",".join(sorted(configs)) + "}"


def _emit_outcome(emit: Progress, prefix: str, o: Outcome) -> None:
    """Emit a candidate's status with its detail and saved log path."""
    detail = f" -- {o.detail}" if o.detail else ""
    emit(f"{prefix}{o.status}{detail}")
    if o.log_path:
        emit(f"[fuzz]     log saved: {o.log_path}")


def _cfg(name: str) -> str:
    """Ensure a symbol name carries the ``CONFIG_`` prefix."""
    return name if name.startswith("CONFIG_") else f"CONFIG_{name}"


def _map(
    items: Sequence[Any], fn: Callable[[Any], Any], run: Dict[str, Any]
) -> List[Any]:
    """Evaluate ``fn`` over items, in parallel or sequentially per ``run``."""
    if run.get("parallel"):
        workers = max(1, int(run.get("workers", 1)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(fn, items))
    return [fn(i) for i in items]


def _subsets(
    strategy: Dict[str, Any], names: Sequence[str]
) -> List[FrozenSet[str]]:
    """Generate candidate subsets for the configured strategy mode.

    ``strategy.limit`` caps the candidate count (0 / absent = no cap).
    """
    mode = strategy.get("mode", "single")
    if mode == "single":
        subs = single_subsets(names)
    elif mode == "random":
        subs = random_subsets(
            list(names),
            int(strategy.get("rounds", 20)),
            int(strategy.get("size", 4)),
            int(strategy.get("seed", 0)),
        )
    else:
        subs = systematic_subsets(names, mode)
    limit = int(strategy.get("limit", 0))
    if limit and len(subs) > limit:
        logger.info(
            "[fuzz] limiting %d candidates to limit=%d", len(subs), limit
        )
        subs = subs[:limit]
    return subs


def _run_opts(fuzz: FuzzConfig) -> Dict[str, Any]:
    """Parallelism options for ``_map`` from the fuzz config."""
    return {"parallel": fuzz.parallel, "workers": fuzz.workers}


def _surface_names(
    fuzz: FuzzConfig,
    nuttx_root: Path,
    profile: Any,
    board_config: str,
    discover_fn: Callable[..., Any],
) -> List[str]:
    """Flat list of ``CONFIG_`` option names for the build sweep surface."""
    s = fuzz.surface
    if s.get("symbols"):
        return [_cfg(n) for n in s["symbols"]]
    if s.get("features"):
        names: List[str] = []
        for configs in s["features"].values():
            names.extend(_cfg(c) for c in configs)
        return names
    scope = s["scope"]
    scope_arg = ",".join(scope) if isinstance(scope, list) else scope
    selector = build_selector(profile, scope_arg, dataload.load_scopes())
    syms = discover_fn(
        nuttx_root,
        board_config,
        profile,
        selector,
        include_choices=s.get("include_choices", False),
    )
    return [_cfg(sym.name) for sym in syms]


def _features_from_surface(surface: Dict[str, Any], require: List[str]) -> Any:
    """Build the ostest/mem feature model from a symbols/features surface."""
    req = ",".join(require) if require else None
    if surface.get("features"):
        specs = [
            f"{name}=" + ",".join(configs)
            for name, configs in surface["features"].items()
        ]
        return parse_features(None, specs, req)
    if surface.get("symbols"):
        return parse_features(",".join(surface["symbols"]), (), req)
    raise CampaignError(
        "ostest/mem surface must set 'symbols' or 'features' (not 'scope')"
    )


def _mem_variants(
    strategy: Dict[str, Any], names: Sequence[str]
) -> List[FrozenSet[str]]:
    """Baseline + systematic variants for a mem sweep, capped at max_builds."""
    mode = strategy.get("mode", "marginal")
    variants: List[FrozenSet[str]] = [frozenset()] + systematic_subsets(
        names, mode if mode in ("marginal", "pairs", "full") else "marginal"
    )
    max_builds = int(strategy.get("max_builds", 64))
    if len(variants) > max_builds:
        logger.info(
            "[fuzz] mem: capping %d variants at max_builds=%d",
            len(variants),
            max_builds,
        )
        variants = variants[:max_builds]
    return variants


def _build_root(build_dir: str) -> str:
    return os.path.join(build_dir, "fuzz")


def plan_candidates(
    fuzz: FuzzConfig,
    target: Optional[Dict[str, Any]] = None,
    *,
    discover_fn: Callable[..., Any] = discover.discover,
) -> List[FrozenSet[str]]:
    """Return the candidate subsets a campaign would evaluate (no builds).

    This is the ``--dry-run`` matrix. ``build`` sweeps candidate config
    subsets directly; ``ostest`` and ``mem`` sweep feature-name subsets and
    include the baseline (the empty set) the engine evaluates first.
    """
    if fuzz.feature == "build":
        profile = dataload.get_profile(fuzz.arch)
        nuttx_root = Path(str(fuzz.tree)) / "nuttx"
        names = _surface_names(
            fuzz, nuttx_root, profile, str(fuzz.board), discover_fn
        )
        return _subsets(fuzz.strategy, names)
    feats, _req = _features_from_surface(fuzz.surface, fuzz.require)
    names = [f.name for f in feats]
    if fuzz.feature == "mem":
        return _mem_variants(fuzz.strategy, names)
    subsets = _subsets(fuzz.strategy, names)
    if not fuzz.strategy.get("skip_baseline"):
        subsets.insert(0, frozenset())
    return subsets


def run_build(
    fuzz: FuzzConfig,
    *,
    discover_fn: Callable[..., Any] = discover.discover,
    build_fn: Callable[..., Outcome] = candidate.build_one,
    progress: Optional[Progress] = None,
) -> FuzzReport:
    """Build-break sweep: build each candidate, classify pass / build-fail.

    ``build`` needs no external target: the fuzz config names the ``board`` and
    the ``tree`` (dir with ``nuttx/`` and ``apps/``) to build.
    """
    emit = progress or _noop
    profile = dataload.get_profile(fuzz.arch)
    patterns = dataload.load_patterns()
    board_config = str(fuzz.board)
    base_conf = build_target_conf(str(fuzz.tree), fuzz.build_dir)
    nuttx_root = Path(str(fuzz.tree)) / "nuttx"
    emit(f"[fuzz] discovering fuzz surface on {board_config} ...")
    names = _surface_names(
        fuzz, nuttx_root, profile, board_config, discover_fn
    )
    subsets = _subsets(fuzz.strategy, names)
    builder = NuttXBuilder(base_conf, rebuild=True)
    build_root = _build_root(fuzz.build_dir)
    logs_dir = os.path.join(build_root, "logs")
    report = FuzzReport(base=board_config, feature="build")
    total = len(subsets)
    emit(f"[fuzz] build sweep: {total} candidate(s) on {board_config}")
    done = itertools.count(1)

    def evaluate(item: Any) -> Outcome:
        idx, cfgs = item
        bd = os.path.join(build_root, f"fuzz-{idx:04d}")
        emit(f"[fuzz] building {_label(cfgs)} ...")
        o = build_fn(
            builder,
            board_config,
            cfgs,
            bd,
            mock=fuzz.mock,
            profile=profile,
            jobs=fuzz.jobs,
            log_dir=logs_dir,
            patterns=patterns,
        )
        _emit_outcome(
            emit, f"[fuzz] [{next(done)}/{total}] {_label(cfgs)}: ", o
        )
        return o

    for o in _map(list(enumerate(subsets)), evaluate, _run_opts(fuzz)):
        report.add(o)
    emit("[fuzz] build sweep complete")
    return report


def run_ostest(  # noqa: C901
    fuzz: FuzzConfig,
    target: Dict[str, Any],
    *,
    build_fn: Callable[..., Outcome] = candidate.build_one,
    run_fn: Callable[..., Outcome] = candidate.run_one,
    progress: Optional[Progress] = None,
) -> FuzzReport:
    """Build+run each candidate under ostest, then ddmin the failures.

    ``target`` is a normal NTFC config (from ``--confpath``): it provides the
    board defconfig, the device (sim / QEMU / serial) and its run parameters.
    """
    emit = progress or _noop
    profile = dataload.get_profile(fuzz.arch)
    patterns = dataload.load_patterns()
    board_config = board_config_of(target)
    feats, req = _features_from_surface(fuzz.surface, fuzz.require)
    fmap: Dict[str, Feature] = {f.name: f for f in feats}
    names = [f.name for f in feats]
    builder = NuttXBuilder(target, rebuild=True)
    build_root = _build_root(target["config"]["build_dir"])
    counter = itertools.count()
    report = FuzzReport(base=board_config, feature="ostest")

    def configs_for(feat_names: FrozenSet[str]) -> FrozenSet[str]:
        cfgs = set(req)
        for n in feat_names:
            cfgs |= fmap[n].configs
        return frozenset(cfgs)

    logs_dir = os.path.join(build_root, "logs")

    def evaluate(feat_names: FrozenSet[str]) -> Outcome:
        bd = os.path.join(build_root, f"fuzz-{next(counter):04d}")
        emit(f"[fuzz] building {_label(feat_names)} ...")
        bo = build_fn(
            builder,
            board_config,
            configs_for(feat_names),
            bd,
            mock=fuzz.mock,
            profile=profile,
            jobs=fuzz.jobs,
            cleanup=False,
            log_dir=logs_dir,
            patterns=patterns,
        )
        try:
            if not bo.ok:
                out = Outcome(
                    feat_names, bo.status, bo.detail, log_path=bo.log_path
                )
                _emit_outcome(emit, f"[fuzz] {_label(feat_names)}: ", out)
                return out
            emit(
                f"[fuzz] running ostest for {_label(feat_names)} "
                f"(up to {fuzz.timeout:g}s) ..."
            )
            core_conf = _core_conf(target, bo.elf_path or "")
            o = run_fn(
                core_conf,
                feat_names,
                patterns,
                fuzz.timeout,
                log_dir=logs_dir,
            )
            _emit_outcome(emit, f"[fuzz] {_label(feat_names)}: ", o)
            return o
        finally:
            shutil.rmtree(bd, ignore_errors=True)

    if not fuzz.strategy.get("skip_baseline"):
        emit("[fuzz] evaluating baseline ...")
        report.baseline = evaluate(frozenset())
        if report.baseline.status == BUILD_FAIL:
            emit("[fuzz] baseline failed to build; aborting sweep.")
            logger.error(
                "[fuzz] baseline failed to build; aborting sweep. Check the "
                "target config and that <cwd>/nuttx and <cwd>/apps exist."
            )
            return report

    subsets = _subsets(fuzz.strategy, names)
    emit(f"[fuzz] ostest sweep: {len(subsets)} candidate(s) on {board_config}")
    for o in _map(subsets, lambda s: evaluate(frozenset(s)), _run_opts(fuzz)):
        report.add(o)

    # Only delta-debug genuine runtime failures; a build-fail does not
    # compile regardless of the subset, so minimising it is meaningless.
    if fuzz.strategy.get("minimize", True):
        for o in report.outcomes:
            if o.status in _RUNTIME_FAILS and len(o.configs) > 1:
                emit(f"[fuzz] minimising {_label(o.configs)} ...")
                minimal = ddmin(
                    sorted(o.configs),
                    lambda s: evaluate(frozenset(s)).status in _RUNTIME_FAILS,
                )
                report.minimized.append((o, frozenset(minimal)))
    return report


def run_mem(  # noqa: C901
    fuzz: FuzzConfig,
    *,
    build_fn: Callable[..., Outcome] = candidate.build_one,
    size_fn: Callable[..., Any] = memsize.elf_size,
    progress: Optional[Progress] = None,
) -> FuzzReport:
    """Memory sweep: build base + variants, diff flash/RAM footprints.

    Like ``build``, ``mem`` only compiles, so the fuzz config names the
    ``board`` and ``tree`` -- no external target config is needed.
    """
    emit = progress or _noop
    profile = dataload.get_profile(fuzz.arch)
    patterns = dataload.load_patterns()
    board_config = str(fuzz.board)
    base_conf = build_target_conf(str(fuzz.tree), fuzz.build_dir)
    feats, req = _features_from_surface(fuzz.surface, fuzz.require)
    fmap: Dict[str, Feature] = {f.name: f for f in feats}
    names = [f.name for f in feats]
    builder = NuttXBuilder(base_conf, rebuild=True)
    build_root = _build_root(fuzz.build_dir)
    logs_dir = os.path.join(build_root, "logs")
    counter = itertools.count()
    report = FuzzReport(base=board_config, feature="mem")

    variants = _mem_variants(fuzz.strategy, names)

    def configs_for(feat_names: FrozenSet[str]) -> FrozenSet[str]:
        cfgs = set(req)
        for n in feat_names:
            cfgs |= fmap[n].configs
        return frozenset(cfgs)

    def evaluate(feat_names: FrozenSet[str]) -> Any:
        bd = os.path.join(build_root, f"mem-{next(counter):04d}")
        emit(f"[fuzz] building + sizing {_label(feat_names)} ...")
        bo = build_fn(
            builder,
            board_config,
            configs_for(feat_names),
            bd,
            mock=fuzz.mock,
            profile=profile,
            jobs=fuzz.jobs,
            cleanup=False,
            log_dir=logs_dir,
            patterns=patterns,
        )
        try:
            if not bo.ok:
                _emit_outcome(emit, f"[fuzz] {_label(feat_names)}: ", bo)
                return feat_names, None, bo
            text, data, bss = size_fn(bo.elf_path)
            return feat_names, memsize.footprint(text, data, bss), bo
        finally:
            shutil.rmtree(bd, ignore_errors=True)

    emit(f"[fuzz] mem sweep: {len(variants)} variant(s) on {board_config}")
    results = _map(variants, lambda s: evaluate(frozenset(s)), _run_opts(fuzz))
    sizes: Dict[FrozenSet[str], Any] = {fn: fp for fn, fp, _ in results}
    for fn, _fp, bo in results:
        if not fn:
            report.baseline = bo
        else:
            report.add(bo)
    base_fp = sizes.get(frozenset())
    if base_fp is None:
        logger.error("[fuzz] mem: baseline did not build; no deltas")
        return report

    for feat_names in variants:
        if not feat_names:
            continue
        fp = sizes.get(feat_names)
        if fp is None:
            continue
        report.memory.append(
            {
                "feature": ",".join(sorted(feat_names)),
                "flash_delta": fp[0] - base_fp[0],
                "ram_delta": fp[1] - base_fp[1],
            }
        )
    return report


def run_campaign(
    fuzz: FuzzConfig,
    target: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> FuzzReport:
    """Dispatch a fuzz config to its engine mode.

    ``target`` is the NTFC target config and is required only for ``ostest``
    (build / mem carry their own build target in the fuzz config).
    """
    if fuzz.feature == "build":
        return run_build(fuzz, **kwargs)
    if fuzz.feature == "mem":
        return run_mem(fuzz, **kwargs)
    if target is None:
        raise CampaignError("ostest needs a target config (--confpath)")
    return run_ostest(fuzz, target, **kwargs)


def _core_conf(  # pragma: no cover
    base_conf: Dict[str, Any], elf_path: str
) -> Dict[str, Any]:
    """Build a single-core NTFC config dict pointing at a built candidate."""
    core: Dict[str, Any] = {}
    for key, val in base_conf.items():
        if "product" in key and isinstance(val, dict):
            cores = val.get("cores", {})
            if cores:
                core = dict(next(iter(cores.values())))
                break
    core["elf_path"] = elf_path
    core["conf_path"] = os.path.join(os.path.dirname(elf_path), ".config")
    core.setdefault("exec_path", elf_path)
    return core
