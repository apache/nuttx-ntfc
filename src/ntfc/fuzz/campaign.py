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

"""Fuzz configuration parsing.

A *fuzz config* is a fuzzer-only YAML file: what to fuzz (feature, surface),
how (strategy, mock), and fuzzer orchestration (workers, jobs). It carries no
NTFC/device concepts.

The build/run *target* is separate:

* ``build`` and ``mem`` only compile, so the fuzz config itself names the build
  target (``board`` + ``tree``) -- a single config is enough.
* ``ostest`` boots a real target, so the target is a normal NTFC config passed
  with ``--confpath`` (sim / QEMU / serial, with all its device/flash options).
  Two configs are used: this fuzz config plus the NTFC target config.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml  # type: ignore

FEATURES = ("build", "ostest", "mem")
_SURFACE_KEYS = ("scope", "symbols", "features")
# Features that only compile and therefore carry their own build target.
_BUILD_ONLY = ("build", "mem")


class CampaignError(ValueError):
    """Invalid fuzz configuration."""


@dataclass
class FuzzConfig:
    """A parsed fuzzer-only configuration."""

    feature: str
    surface: Dict[str, Any]
    strategy: Dict[str, Any]
    arch: str = "stm32"
    mock: bool = False
    require: List[str] = field(default_factory=list)
    timeout: float = 90.0
    workers: int = 1
    jobs: Optional[int] = None
    parallel: bool = False
    # Build target for build/mem (unused for ostest -- that target is the
    # NTFC config passed via --confpath):
    board: Optional[str] = None
    tree: Optional[str] = None
    build_dir: str = "./build"

    @property
    def needs_target(self) -> bool:
        """Whether this feature needs an external NTFC target config."""
        return self.feature not in _BUILD_ONLY


def _load_yaml(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise CampaignError(f"file not found: {path}") from exc
    if not isinstance(data, dict):
        raise CampaignError(f"not a YAML mapping: {path}")
    return data


def board_config_of(target_conf: Dict[str, Any]) -> str:
    """Derive the ``board:config`` string from an NTFC config's defconfig.

    A defconfig path ``boards/<arch>/<chip>/<board>/configs/<config>`` yields
    ``<board>:<config>``.
    """
    for key, val in target_conf.items():
        if "product" not in key or not isinstance(val, dict):
            continue
        for core in val.get("cores", {}).values():
            defconfig = core.get("defconfig")
            if not defconfig:
                continue
            parts = defconfig.strip("/").split("/")
            if "configs" in parts:
                idx = parts.index("configs")
                return f"{parts[idx - 1]}:{parts[idx + 1]}"
    raise CampaignError("no core defconfig found in target config")


def build_target_conf(tree: str, build_dir: str) -> Dict[str, Any]:
    """Minimal NuttXBuilder config for a build-only target (build/mem).

    NuttXBuilder only needs ``config.cwd`` (the dir containing ``nuttx/`` and
    ``apps/``) and ``config.build_dir``; the board is passed to it directly.
    """
    return {"config": {"cwd": tree, "build_dir": build_dir}}


def load_fuzz_config(path: str) -> FuzzConfig:
    """Load and validate a fuzzer-only config file."""
    doc = _load_yaml(path)

    feature = doc.get("feature")
    if feature not in FEATURES:
        raise CampaignError(
            f"'feature' must be one of {FEATURES}, got {feature!r}"
        )

    surface = doc.get("surface") or {}
    if not any(surface.get(k) for k in _SURFACE_KEYS):
        raise CampaignError(
            "'surface' must set one of scope / symbols / features"
        )

    strategy = dict(doc.get("strategy") or {})
    strategy.setdefault("mode", "single")

    board = doc.get("board")
    tree = doc.get("tree")
    if feature in _BUILD_ONLY:
        if not board:
            raise CampaignError(
                f"'{feature}' needs a 'board' (board:config) to build"
            )
        if not tree:
            raise CampaignError(
                f"'{feature}' needs a 'tree' (dir with nuttx/ and apps/)"
            )

    return FuzzConfig(
        feature=feature,
        surface=surface,
        strategy=strategy,
        arch=doc.get("arch", "stm32"),
        mock=bool(doc.get("mock", False)),
        require=list(doc.get("require") or []),
        timeout=float(doc.get("timeout", 90.0)),
        workers=int(doc.get("workers", 1)),
        jobs=doc.get("jobs"),
        parallel=bool(doc.get("parallel", False)),
        board=board,
        tree=tree,
        build_dir=doc.get("build_dir", "./build"),
    )
