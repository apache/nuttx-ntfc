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

"""Candidate subset generation and delta-debug minimization.

Pure functions over lists of names (symbols or feature names): the
single-option sweep, random subsets, systematic subsets (marginal / pairs /
full), and ``ddmin`` to reduce a failing subset to a minimal one. Ported from
the standalone fuzzer; baseline handling is left to the caller, and
``SystemExit`` is replaced with ``ValueError``.
"""

import itertools
import random
from typing import Callable, FrozenSet, List, Sequence


def single_subsets(names: Sequence[str]) -> List[FrozenSet[str]]:
    """Return one singleton subset per name (the build-break sweep)."""
    return [frozenset([n]) for n in names]


def random_subsets(
    names: Sequence[str], rounds: int, size: int, seed: int
) -> List[FrozenSet[str]]:
    """Return ``rounds`` random subsets of 1..``size`` names, seeded."""
    rng = random.Random(seed)
    subs: List[FrozenSet[str]] = []
    names = list(names)
    hi = max(1, min(size, len(names)))
    for _ in range(rounds):
        k = rng.randint(1, hi)
        subs.append(frozenset(rng.sample(names, k)))
    return subs


def systematic_subsets(
    names: Sequence[str], mode: str
) -> List[FrozenSet[str]]:
    """Deterministic subsets for a systematic mode (no baseline included).

    marginal: each name alone, plus the all-on set.
    pairs:    each name alone, plus every unordered pair.
    full:     every non-empty subset.
    """
    names = list(names)
    subs: List[FrozenSet[str]] = []
    if mode == "marginal":
        subs = [frozenset([n]) for n in names]
        if len(names) > 1:
            subs.append(frozenset(names))
    elif mode == "pairs":
        subs = [frozenset([n]) for n in names]
        subs += [frozenset(c) for c in itertools.combinations(names, 2)]
    elif mode == "full":
        for r in range(1, len(names) + 1):
            subs += [frozenset(c) for c in itertools.combinations(names, r)]
    else:
        raise ValueError(f"unknown mode '{mode}'")

    seen = set()
    uniq: List[FrozenSet[str]] = []
    for s in subs:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def ddmin(
    items: Sequence[str], fails: Callable[[List[str]], bool]
) -> List[str]:
    """Delta-debug to a minimal failing subset.

    ``fails(subset)`` returns True when the subset still reproduces the
    failure. Returns the smallest sublist for which ``fails`` stays True.
    """
    items = list(items)
    n = 2
    while len(items) > 1:
        size = max(1, len(items) // n)
        chunks = [items[i : i + size] for i in range(0, len(items), size)]
        for ch in chunks:
            complement = [x for x in items if x not in ch]
            if complement and fails(complement):
                items = complement
                n = max(n - 1, 2)
                break
        else:
            if n >= len(items):
                break
            n = min(len(items), n * 2)
    return items
