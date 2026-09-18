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

from pathlib import Path

from ntfc.fuzz import dataload
from ntfc.fuzz.mocks import append_mock_defines, missing_board_constants


def test_mocks_gpio_pin_with_suggestion():
    p = dataload.get_profile("stm32")
    log = (
        "error: 'GPIO_CAN2_RX' undeclared (first use in this function); "
        "did you mean 'GPIO_CAN2_RX_1'?"
    )
    out = missing_board_constants(log, p)
    assert out.get("GPIO_CAN2_RX") == "GPIO_CAN2_RX_1"


def test_mocks_undeclared_without_suggestion_gets_zero():
    p = dataload.get_profile("stm32")
    log = "error: 'BOARD_LTDC_HEIGHT' undeclared here (not in a function)"
    assert missing_board_constants(log, p) == {"BOARD_LTDC_HEIGHT": "0"}


def test_mocks_must_be_defined_gets_one():
    p = dataload.get_profile("stm32")
    log = "#error BOARD_LTDC_WIDTH must be defined in the board.h header file"
    assert missing_board_constants(log, p) == {"BOARD_LTDC_WIDTH": "1"}


def test_mocks_non_board_identifier_ignored():
    p = dataload.get_profile("stm32")
    log = "error: 'some_local_var' undeclared"
    assert missing_board_constants(log, p) == {}


def test_mocks_suffix_clkin_is_mockable():
    p = dataload.get_profile("stm32")
    log = "error: 'STM32_TIM6_CLKIN' undeclared"
    assert missing_board_constants(log, p) == {"STM32_TIM6_CLKIN": "0"}


def test_mocks_must_be_defined_non_board_ignored():
    p = dataload.get_profile("stm32")
    log = "#error SOMETHING must be defined in the header file"
    assert missing_board_constants(log, p) == {}


def test_append_mock_defines_writes_block(tmp_path):
    cfg = Path(tmp_path) / "config.h"
    cfg.write_text("#define CONFIG_FOO 1\n")
    append_mock_defines(cfg, {"GPIO_CAN2_RX": "GPIO_CAN2_RX_1"})
    text = cfg.read_text()
    assert "#define GPIO_CAN2_RX GPIO_CAN2_RX_1" in text
    assert "#define CONFIG_FOO 1" in text  # original preserved


def test_append_mock_defines_empty_is_noop(tmp_path):
    cfg = Path(tmp_path) / "config.h"
    cfg.write_text("#define CONFIG_FOO 1\n")
    append_mock_defines(cfg, {})
    assert cfg.read_text() == "#define CONFIG_FOO 1\n"
