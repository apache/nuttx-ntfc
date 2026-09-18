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

import dataclasses

import pytest

from ntfc.fuzz.features import Feature, normalize, parse_features


def test_options_each_its_own_feature():
    feats, req = parse_features("CONFIG_FS_FAT,CONFIG_CRYPTO", (), None)
    names = {f.name for f in feats}
    assert names == {"CONFIG_FS_FAT", "CONFIG_CRYPTO"}
    assert req == frozenset()


def test_options_configs_carry_prefix():
    feats, _ = parse_features("FS_FAT", (), None)
    assert feats[0].configs == frozenset({"CONFIG_FS_FAT"})


def test_named_feature_group():
    feats, req = parse_features(
        None, ("net=CONFIG_NET,CONFIG_NETDEV_LATEINIT",), None
    )
    assert feats[0].name == "net"
    assert feats[0].configs == frozenset(
        {"CONFIG_NET", "CONFIG_NETDEV_LATEINIT"}
    )


def test_require_parsed():
    _, req = parse_features("CONFIG_A", (), "CONFIG_SCHED_HPWORK")
    assert req == frozenset({"CONFIG_SCHED_HPWORK"})


def test_duplicate_feature_raises():
    # an --options entry and a --feature group resolving to the same name
    with pytest.raises(ValueError):
        parse_features("CONFIG_A", ("CONFIG_A=CONFIG_B",), None)


def test_empty_raises():
    with pytest.raises(ValueError):
        parse_features(None, (), None)


def test_normalize_strips_prefix_and_dedups():
    assert normalize(["CONFIG_A", "A", " B "]) == ["A", "B"]


def test_normalize_skips_empty_tokens():
    assert normalize(["", "  ", "A"]) == ["A"]


def test_feature_spec_without_name_uses_first_config():
    feats, _ = parse_features(None, ("CONFIG_NET,CONFIG_NETDEV",), None)
    assert feats[0].name == "CONFIG_NET"
    assert feats[0].configs == frozenset({"CONFIG_NET", "CONFIG_NETDEV"})


def test_empty_feature_group_raises():
    with pytest.raises(ValueError):
        parse_features(None, ("=",), None)


def test_feature_is_frozen():
    f = Feature("x", frozenset({"CONFIG_X"}))
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.name = "y"  # type: ignore[misc]
