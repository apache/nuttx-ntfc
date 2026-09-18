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

import re

import pytest

from ntfc.fuzz import dataload
from ntfc.fuzz.dataload import FuzzDataError


def test_load_profiles_stm32():
    profiles = dataload.load_profiles()
    assert "stm32" in profiles
    p = profiles["stm32"]
    assert p.name == "stm32"
    assert p.symbol_path_re.search("arch/arm/src/stm32h7/Kconfig")
    assert p.symbol_path_re.search("arch/arm/src/common/stm32/Kconfig")
    assert not p.symbol_path_re.search("net/Kconfig")
    assert p.skip_prefixes == (
        "STM32_HAVE",
        "ARCH_CHIP",
        "STM32_FLASH_CONFIG_",
    )
    assert "GPIO_" in p.mockable_prefixes
    assert p.mockable_suffixes == ("_CLKIN", "_FREQUENCY")


def test_board_required_merges_generic_and_extra():
    p = dataload.get_profile("stm32")
    br = p.board_required_re()
    assert br.search("BOARD_LTDC_WIDTH must be defined")  # generic
    assert br.search("selected HSI48 as USB clock")  # stm32 extra


def test_get_profile_unknown_raises_listing_known():
    with pytest.raises(FuzzDataError) as exc:
        dataload.get_profile("does-not-exist")
    assert "stm32" in str(exc.value)


def test_load_scopes_has_net_and_kernel():
    scopes = dataload.load_scopes()
    assert re.compile(scopes["net"]).search("net/Kconfig")
    assert re.compile(scopes["kernel"]).search("sched/Kconfig")


def test_load_patterns_keys():
    pats = dataload.load_patterns()
    assert re.compile(pats["ostest_exit"]).search(
        "ostest_main: Exiting with status 0"
    )
    assert isinstance(pats["board_required"], list)


def test_missing_data_file_raises(tmp_path):
    with pytest.raises(FuzzDataError) as exc:
        dataload.load_scopes(data_dir=tmp_path)
    assert "not found" in str(exc.value)


def test_patterns_missing_key_raises(tmp_path):
    (tmp_path / "patterns.yaml").write_text("crash: x\n")
    with pytest.raises(FuzzDataError) as exc:
        dataload.load_patterns(data_dir=tmp_path)
    assert "missing key" in str(exc.value)
