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

from ntfc.fuzz.campaign import (
    CampaignError,
    board_config_of,
    build_target_conf,
    load_fuzz_config,
)

BUILD = "tests/fuzz/resources/campaign-build.yaml"
OSTEST = "tests/fuzz/resources/campaign-ostest.yaml"


def test_load_build_config():
    c = load_fuzz_config(BUILD)
    assert c.feature == "build"
    assert c.surface["scope"] == ["can"]
    assert c.arch == "stm32"
    assert c.mock is True
    assert c.board == "sim:ntfc"
    assert c.tree == "./external"
    assert c.workers == 2
    assert c.needs_target is False


def test_load_ostest_config_needs_target():
    c = load_fuzz_config(OSTEST)
    assert c.feature == "ostest"
    assert c.needs_target is True
    # ostest carries no build target -- it comes from the NTFC target config
    assert c.board is None
    assert c.tree is None


def test_defaults_applied(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "feature: build\nboard: sim:nsh\ntree: .\nsurface: {symbols: [CAN]}\n"
    )
    c = load_fuzz_config(str(p))
    assert c.strategy["mode"] == "single"
    assert c.mock is False
    assert c.timeout == 90
    assert c.parallel is False
    assert c.require == []
    assert c.build_dir == "./build"


def test_missing_feature_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("surface: {symbols: [X]}\n")
    with pytest.raises(CampaignError, match="feature"):
        load_fuzz_config(str(p))


def test_bad_feature_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("feature: nonsense\nsurface: {symbols: [X]}\n")
    with pytest.raises(CampaignError, match="feature"):
        load_fuzz_config(str(p))


def test_missing_surface_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("feature: ostest\nsurface: {}\n")
    with pytest.raises(CampaignError, match="surface"):
        load_fuzz_config(str(p))


def test_build_without_board_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("feature: build\ntree: .\nsurface: {symbols: [X]}\n")
    with pytest.raises(CampaignError, match="board"):
        load_fuzz_config(str(p))


def test_build_without_tree_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("feature: mem\nboard: sim:nsh\nsurface: {symbols: [X]}\n")
    with pytest.raises(CampaignError, match="tree"):
        load_fuzz_config(str(p))


def test_file_not_found_raises(tmp_path):
    with pytest.raises(CampaignError, match="not found"):
        load_fuzz_config(str(tmp_path / "nope.yaml"))


def test_not_a_mapping_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("- a\n- b\n")
    with pytest.raises(CampaignError, match="mapping"):
        load_fuzz_config(str(p))


def test_board_config_of_target():
    target = {
        "product": {
            "cores": {"c0": {"defconfig": "boards/sim/sim/sim/configs/nsh"}}
        }
    }
    assert board_config_of(target) == "sim:nsh"


def test_board_config_of_skips_nonproduct_and_defconfigless():
    target = {
        "config": {"cwd": "x"},
        "product": {
            "cores": {
                "c0": {"device": "sim"},
                "c1": {"defconfig": "boards/sim/sim/sim/configs/nsh"},
            }
        },
    }
    assert board_config_of(target) == "sim:nsh"


def test_board_config_of_without_configs_segment():
    target = {
        "product": {
            "cores": {
                "c0": {"defconfig": "weird/path"},
                "c1": {"defconfig": "boards/sim/sim/sim/configs/nsh"},
            }
        }
    }
    assert board_config_of(target) == "sim:nsh"


def test_board_config_of_missing_raises():
    with pytest.raises(CampaignError, match="defconfig"):
        board_config_of({"product": {"cores": {"c0": {"device": "sim"}}}})


def test_build_target_conf_shape():
    conf = build_target_conf("/x/tree", "/x/build")
    assert conf["config"]["cwd"] == "/x/tree"
    assert conf["config"]["build_dir"] == "/x/build"
