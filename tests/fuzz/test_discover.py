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

from types import SimpleNamespace

from ntfc.fuzz import dataload, discover
from ntfc.fuzz.discover import discover_fuzzable


def _sym(
    name, filename, value="n", assignable=(0, 2), choice=None, prompt=True
):
    node = SimpleNamespace(filename=filename, prompt=prompt)
    return SimpleNamespace(
        name=name,
        type=discover.BOOL,
        str_value=value,
        assignable=assignable,
        choice=choice,
        nodes=[node],
    )


def _nonbool_sym(name, filename):
    node = SimpleNamespace(filename=filename, prompt=True)
    return SimpleNamespace(
        name=name,
        type=object(),  # not discover.BOOL
        str_value="n",
        assignable=(0, 2),
        choice=None,
        nodes=[node],
    )


class _FakeKconf:
    def __init__(self, syms):
        self.unique_defined_syms = syms


def test_discovers_settable_arch_bool():
    p = dataload.get_profile("stm32")
    sel = p.symbol_path_re
    syms = [
        _sym("STM32_ADC2", "arch/arm/src/stm32h7/Kconfig"),  # keep
        _sym("STM32_HAVE_ADC2", "arch/arm/src/stm32h7/Kconfig"),  # skip prefix
        _sym("NET_TCP", "net/Kconfig"),  # out of scope
        _sym(
            "STM32_ADC1", "arch/arm/src/stm32h7/Kconfig", value="y"
        ),  # already y
        _sym(
            "STM32_ADC3", "arch/arm/src/stm32h7/Kconfig", assignable=(0,)
        ),  # not settable
        _sym(
            "STM32_ADC4", "arch/arm/src/stm32h7/Kconfig", prompt=False
        ),  # no prompt
        _nonbool_sym(
            "STM32_UART5_RXDMA", "arch/arm/src/stm32h7/Kconfig"
        ),  # not a bool
    ]
    out = discover_fuzzable(_FakeKconf(syms), profile=p, selector=sel)
    assert [s.name for s in out] == ["STM32_ADC2"]
    assert out[0].target == "y"
    assert out[0].kind == "bool"


def test_include_choices_toggle():
    p = dataload.get_profile("stm32")
    sel = p.symbol_path_re
    choice = object()
    syms = [
        _sym(
            "STM32_CHOICEMEMBER", "arch/arm/src/stm32h7/Kconfig", choice=choice
        )
    ]
    assert discover_fuzzable(_FakeKconf(syms), p, sel) == []
    got = discover_fuzzable(_FakeKconf(syms), p, sel, include_choices=True)
    assert [s.name for s in got] == ["STM32_CHOICEMEMBER"]
    assert got[0].in_choice is True
