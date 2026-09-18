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

"""Load the fuzzer's externalized data tables into runtime objects.

The fuzzer's slowly-changing knowledge (arch profiles, scope vocabulary,
classification regexes) lives in editable YAML files under ``data/``, shipped
as package data. This module reads them and produces the objects the engine
consumes, so no engine code carries literal tables. Pass ``data_dir`` to load
an alternative set (e.g. a campaign-supplied override directory).
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml  # type: ignore

from ntfc.fuzz.profiles import ArchProfile

DATA_DIR = Path(__file__).resolve().parent / "data"


class FuzzDataError(Exception):
    """Invalid or missing fuzz data file."""


def _read(name: str, data_dir: Optional[Path]) -> Any:
    path = (data_dir or DATA_DIR) / name
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise FuzzDataError(f"fuzz data file not found: {path}") from exc


def load_patterns(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load the classification regex tables."""
    data: Dict[str, Any] = _read("patterns.yaml", data_dir)
    for key in (
        "board_required",
        "config_required",
        "build_error",
        "ostest_exit",
        "crash",
    ):
        if key not in data:
            raise FuzzDataError(f"patterns.yaml missing key '{key}'")
    return data


def load_scopes(data_dir: Optional[Path] = None) -> Dict[str, str]:
    """Load the subsystem -> path-regex scope vocabulary."""
    return dict(_read("scopes.yaml", data_dir))


def load_profiles(
    data_dir: Optional[Path] = None,
) -> Dict[str, ArchProfile]:
    """Load the arch profile registry, merging in the generic patterns."""
    raw = _read("arch-profiles.yaml", data_dir)
    pats = load_patterns(data_dir)
    gbr = tuple(pats["board_required"])
    gcr = tuple(pats["config_required"])
    out: Dict[str, ArchProfile] = {}
    for name, spec in raw.items():
        out[name] = ArchProfile(
            name=name,
            symbol_path_re=re.compile(spec["symbol_path"]),
            skip_prefixes=tuple(spec.get("skip_prefixes", ())),
            mockable_prefixes=tuple(spec.get("mockable_prefixes", ())),
            mockable_suffixes=tuple(spec.get("mockable_suffixes", ())),
            extra_board_required=tuple(spec.get("extra_board_required", ())),
            generic_board_required=gbr,
            generic_config_required=gcr,
        )
    return out


def get_profile(name: str, data_dir: Optional[Path] = None) -> ArchProfile:
    """Return one arch profile by name, or raise listing the known names."""
    profiles = load_profiles(data_dir)
    try:
        return profiles[name]
    except KeyError as exc:
        known = ", ".join(sorted(profiles))
        raise FuzzDataError(
            f"unknown arch '{name}'; known profiles: {known}"
        ) from exc
