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

import pytest

from ntfc.fuzz import dataload
from ntfc.fuzz.dataload import FuzzDataError
from ntfc.fuzz.profiles import build_selector


def _fixture():
    return dataload.get_profile("stm32"), dataload.load_scopes()


def test_selector_none_is_arch_surface():
    p, scopes = _fixture()
    sel = build_selector(p, None, scopes)
    assert sel.search("arch/arm/src/stm32h7/Kconfig")


def test_selector_named_scopes():
    p, scopes = _fixture()
    sel = build_selector(p, "net,fs", scopes)
    assert sel.search("net/Kconfig")
    assert sel.search("fs/vfs/Kconfig")
    assert not sel.search("arch/arm/src/stm32h7/Kconfig")


def test_selector_all_matches_everything():
    p, scopes = _fixture()
    sel = build_selector(p, "all", scopes)
    assert sel.search("anything/at/all")


def test_selector_arch_scope():
    p, scopes = _fixture()
    sel = build_selector(p, "arch", scopes)
    assert sel.search("arch/arm/src/stm32h7/Kconfig")
    assert not sel.search("net/Kconfig")


def test_selector_unknown_raises():
    p, scopes = _fixture()
    with pytest.raises(FuzzDataError):
        build_selector(p, "nonsense", scopes)


def test_config_required_re():
    p = dataload.get_profile("stm32")
    cr = p.config_required_re()
    assert cr.search("feature requires CONFIG_NET")


def test_is_arch_symbol():
    p = dataload.get_profile("stm32")
    in_arch = SimpleNamespace(
        nodes=[SimpleNamespace(filename="arch/arm/src/stm32h7/Kconfig")]
    )
    not_arch = SimpleNamespace(nodes=[SimpleNamespace(filename="net/Kconfig")])
    assert p.is_arch_symbol(in_arch) is True
    assert p.is_arch_symbol(not_arch) is False
