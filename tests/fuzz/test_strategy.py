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

import pytest

from ntfc.fuzz import strategy


def test_single_subsets():
    subs = strategy.single_subsets(["A", "B", "C"])
    assert subs == [frozenset({"A"}), frozenset({"B"}), frozenset({"C"})]


def test_random_subsets_deterministic_with_seed():
    a = strategy.random_subsets(["A", "B", "C", "D"], rounds=5, size=3, seed=1)
    b = strategy.random_subsets(["A", "B", "C", "D"], rounds=5, size=3, seed=1)
    assert a == b
    assert len(a) == 5
    assert all(1 <= len(s) <= 3 for s in a)


def test_systematic_marginal():
    subs = strategy.systematic_subsets(["A", "B"], "marginal")
    assert frozenset({"A"}) in subs
    assert frozenset({"A", "B"}) in subs


def test_systematic_marginal_single_name_has_no_all_on():
    subs = strategy.systematic_subsets(["A"], "marginal")
    assert subs == [frozenset({"A"})]


def test_systematic_pairs():
    subs = strategy.systematic_subsets(["A", "B", "C"], "pairs")
    assert frozenset({"A", "B"}) in subs
    assert frozenset({"A"}) in subs


def test_systematic_full_covers_all_nonempty_subsets():
    subs = strategy.systematic_subsets(["A", "B"], "full")
    assert set(subs) == {
        frozenset({"A"}),
        frozenset({"B"}),
        frozenset({"A", "B"}),
    }


def test_systematic_unknown_mode_raises():
    with pytest.raises(ValueError):
        strategy.systematic_subsets(["A"], "bogus")


def test_systematic_subsets_are_unique():
    subs = strategy.systematic_subsets(["A", "A"], "pairs")
    assert len(subs) == len(set(subs))


def test_ddmin_finds_single_culprit():
    minimal = strategy.ddmin(["A", "B", "C", "D"], lambda s: "C" in s)
    assert minimal == ["C"]


def test_ddmin_irreducible_set_increases_granularity():
    # only the full set reproduces the failure: ddmin must increase
    # granularity (no single-chunk complement fails) and return everything.
    items = ["A", "B", "C", "D"]
    minimal = strategy.ddmin(items, lambda s: set(s) == {"A", "B", "C", "D"})
    assert sorted(minimal) == items
