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

"""Kconfig symbol discovery via kconfiglib.

Configures a base board with Make so the apps preconfig and arch/board Kconfig
symlinks exist, then parses the tree to enumerate fuzzable symbols. The
environment setup mirrors ``tools/checkkconfig.py`` (the proven recipe). Ported
from the standalone fuzzer; the NuttX checkout is passed as a plain path
instead of the fuzzer's ``Repo`` object.
"""

import contextlib
import os
import re  # noqa: F401  (used in string type annotations)
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, List, Optional

from ntfc.log.logger import logger

try:
    from kconfiglib import BOOL, Kconfig  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    logger.error(
        "the fuzz feature depends on kconfiglib. Install it: "
        "pip install kconfiglib"
    )
    raise

from ntfc.fuzz.model import SymbolInfo

if TYPE_CHECKING:
    from ntfc.fuzz.profiles import ArchProfile


def _run(
    cmd: List[str], cwd: Path
) -> "subprocess.CompletedProcess[str]":  # pragma: no cover
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


@contextlib.contextmanager
def kconfig_env(  # pragma: no cover
    nuttx_root: Path, board_config: str
) -> Iterator["Kconfig"]:
    """Configure the board, yield a loaded Kconfig, then distclean."""
    nuttx_root = Path(nuttx_root).resolve()
    r = _run(
        [str(nuttx_root / "tools" / "configure.sh"), "-E", board_config],
        nuttx_root,
    )
    if r.returncode != 0:
        if (nuttx_root / ".config").exists():
            _run(["make", "distclean"], nuttx_root)
        raise RuntimeError(
            f"configure.sh failed for {board_config}\n" f"{r.stdout}{r.stderr}"
        )

    saved = {
        k: os.environ.get(k)
        for k in (
            "APPSDIR",
            "APPSBINDIR",
            "EXTERNALDIR",
            "BINDIR",
            "KCONFIG_CONFIG",
        )
    }
    os.environ["APPSDIR"] = "../apps"
    os.environ["APPSBINDIR"] = "../apps"
    os.environ["EXTERNALDIR"] = "dummy"
    os.environ["BINDIR"] = str(nuttx_root)
    os.environ["KCONFIG_CONFIG"] = str(nuttx_root / ".config")

    cwd = os.getcwd()
    try:
        os.chdir(nuttx_root)
        kconf = Kconfig("Kconfig", warn=True, warn_to_stderr=False)
        kconf.load_config()
        yield kconf
    finally:
        os.chdir(cwd)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if (nuttx_root / ".config").exists():
            _run(["make", "distclean"], nuttx_root)


def _in_scope(sym: object, selector: "re.Pattern[str]") -> bool:
    return any(
        selector.search(n.filename or "")
        for n in sym.nodes  # type: ignore[attr-defined]
    )


def discover_fuzzable(
    kconf: "Kconfig",
    profile: "ArchProfile",
    selector: "re.Pattern[str]",
    include_choices: bool = False,
) -> List[SymbolInfo]:
    """Return settable bool symbols in the selector's scope.

    A symbol qualifies when it is a ``bool`` in ``selector``'s scope, is not a
    skipped-prefix capability flag, is currently ``n``, and can be set to ``y``
    in the expanded base config.
    """
    out: List[SymbolInfo] = []
    for sym in kconf.unique_defined_syms:
        if not _in_scope(sym, selector):
            continue
        if sym.type != BOOL:
            continue
        if sym.name.startswith(profile.skip_prefixes):
            continue
        if sym.choice is not None and not include_choices:
            continue
        if not any(n.prompt for n in sym.nodes):
            continue
        if sym.str_value != "n":
            continue
        if 2 not in sym.assignable:  # 2 == y
            continue
        out.append(
            SymbolInfo(
                name=sym.name,
                kind="bool",
                cur_value=sym.str_value,
                target="y",
                files=sorted({n.filename for n in sym.nodes if n.filename}),
                in_choice=sym.choice is not None,
            )
        )
    out.sort(key=lambda s: s.name)
    return out


def discover(  # pragma: no cover
    nuttx_root: Path,
    board_config: str,
    profile: "ArchProfile",
    selector: "re.Pattern[str]",
    include_choices: bool = False,
    only: Optional[List[str]] = None,
) -> List[SymbolInfo]:
    """Configure the board, discover fuzzable symbols, optionally filter."""
    with kconfig_env(nuttx_root, board_config) as kconf:
        syms = discover_fuzzable(
            kconf,
            profile=profile,
            selector=selector,
            include_choices=include_choices,
        )
    if only:
        wanted = set(only)
        syms = [s for s in syms if s.name in wanted]
    return syms
