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

from ntfc.lib.elf.elf_parser import ElfParser


def test_lib_elf_parser():
    with pytest.raises(AttributeError):
        _ = ElfParser("xxx")

    with pytest.raises(AttributeError):
        _ = ElfParser("./tests/resources/nuttx/sim/kv_config")

    a = ElfParser("./tests/resources/nuttx/sim/nuttx")

    assert a.has_symbol("hello_main") is True
    assert a.has_symbol("dummy_main") is False
    assert a.has_symbol(re.compile("hello")) is True
    assert a.has_symbol(re.compile("dummy_main")) is False

    assert a.get_symbols_by_pattern("hello", "main")[0].name == "hello_main"
    assert len(a.get_symbols_by_pattern("", "main")) > 1
    assert a.get_symbols_by_pattern("dummy", "main") == []

    with pytest.raises(ValueError):
        _ = a.has_symbol(b"xx")


def _nm_output(mocker, lines):
    result = mocker.Mock()
    result.stdout = "\n".join(lines)
    return mocker.patch(
        "ntfc.lib.elf.elf_parser.subprocess.run", return_value=result
    )


def test_lib_elf_parser_label_prefix(mocker):
    _nm_output(
        mocker,
        [
            "00000100 T _nx_start",
            "00000200 T _ostest_main",
            "00000300 T __start",
            "00000400 T rh850_vector",
        ],
    )

    a = ElfParser("./tests/resources/nuttx/sim/nuttx")

    assert a.has_symbol("nx_start") is True
    assert a.has_symbol("ostest_main") is True
    assert a.has_symbol("_ostest_main") is False
    assert a.has_symbol("_start") is True
    assert a.has_symbol("rh850_vector") is True
    assert a.get_symbols_by_pattern("ostest", "main")[0].name == "ostest_main"


def test_lib_elf_parser_no_label_prefix(mocker):
    _nm_output(
        mocker,
        [
            "00000100 T nx_start",
            "00000200 T _ostest_main",
        ],
    )

    a = ElfParser("./tests/resources/nuttx/sim/nuttx")

    assert a.has_symbol("_ostest_main") is True
    assert a.has_symbol("ostest_main") is False

    _nm_output(mocker, ["00000100 T _foo_main"])

    b = ElfParser("./tests/resources/nuttx/sim/nuttx")

    assert b.has_symbol("_foo_main") is True


def test_lib_elf_parser_label_prefix_app_binary(mocker):
    # kernel-mode application binaries have main, not nx_start
    _nm_output(
        mocker,
        [
            "00000100 T _main",
            "00000200 T _hello_main",
        ],
    )

    a = ElfParser("./tests/resources/nuttx/sim/nuttx")

    assert a.has_symbol("main") is True
    assert a.has_symbol("hello_main") is True
    assert a.has_symbol(re.compile("^hello")) is True


def _fields(parser):
    return [(s.name, s.address, s.type) for s in parser.symbols]


def test_lib_elf_parser_short_lines(mocker):
    _nm_output(
        mocker,
        [
            "00000100 T nx_start",
            "T _hello_main",
            "_ostest_main",
        ],
    )

    a = ElfParser("./tests/resources/nuttx/sim/nuttx")

    assert _fields(a) == [
        ("nx_start", "00000100", "T"),
        ("_hello_main", "", "T"),
        ("_ostest_main", "", ""),
    ]


def test_lib_elf_parser_short_lines_label_prefix(mocker):
    _nm_output(
        mocker,
        [
            "00000100 T _nx_start",
            "T _hello_main",
            "_ostest_main",
        ],
    )

    a = ElfParser("./tests/resources/nuttx/sim/nuttx")

    assert _fields(a) == [
        ("nx_start", "00000100", "T"),
        ("hello_main", "", "T"),
        ("ostest_main", "", ""),
    ]
