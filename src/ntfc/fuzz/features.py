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

"""The fuzzer feature model.

A *feature* is a named set of ``CONFIG`` options enabled together and treated
as one unit. It may be a single option (the common case) or a group that only
builds when several options are set together (e.g. NET needs a device). A
shared prerequisite context (``require``) can be enabled in every build. Ported
from the standalone ``kconfmem`` module; ``SystemExit`` is replaced with
``ValueError`` so callers can handle bad input.
"""

from dataclasses import dataclass
from typing import FrozenSet, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Feature:
    """A named set of CONFIG options treated as one unit."""

    name: str
    configs: FrozenSet[str]


def normalize(options: Sequence[str]) -> List[str]:
    """Bare option names (strip an optional CONFIG_ prefix), de-duplicated."""
    out: List[str] = []
    for o in options:
        o = o.strip()
        if not o:
            continue
        if o.startswith("CONFIG_"):
            o = o[len("CONFIG_") :]
        if o not in out:
            out.append(o)
    return out


def parse_features(
    options: Optional[str],
    feature_specs: Sequence[str],
    require: Optional[str],
) -> Tuple[List[Feature], FrozenSet[str]]:
    """Build the feature list from single-config options and grouped features.

    :param options: comma-separated ``CONFIG_*`` options, each its own feature.
    :param feature_specs: ``NAME=CONFIG_A,CONFIG_B`` group strings.
    :param require: comma-separated always-on prerequisite options.
    :return: ``(features, require_set)``. Configs keep the ``CONFIG_`` prefix.
    :raises ValueError: on empty or malformed input.
    """
    features: List[Feature] = []
    seen = set()

    def add(name: str, configs: Sequence[str]) -> None:
        if name in seen:
            raise ValueError(f"duplicate feature name '{name}'")
        seen.add(name)
        features.append(
            Feature(name, frozenset(f"CONFIG_{c}" for c in configs))
        )

    if options:
        for c in normalize(options.split(",")):
            add(c if c.startswith("CONFIG_") else f"CONFIG_{c}", [c])

    for spec in feature_specs:
        if "=" in spec:
            name, rest = spec.split("=", 1)
            name = name.strip()
        else:
            name, rest = "", spec
        configs = normalize(rest.split(","))
        if not configs:
            raise ValueError(f"empty feature: '{spec}'")
        add(name or f"CONFIG_{configs[0]}", configs)

    req = (
        frozenset(f"CONFIG_{c}" for c in normalize(require.split(",")))
        if require
        else frozenset()
    )
    if not features:
        raise ValueError("no options/features given")
    return features, req
