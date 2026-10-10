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
import time

import pytest

from ntfc.command_builder import CommandBuilder, EncodedCommand


@pytest.fixture
def builder() -> CommandBuilder:
    return CommandBuilder(prompt=b"nsh> ", no_cmd="command not found")


def test_encoded_command_dataclass() -> None:
    ec = EncodedCommand(cmd=b"test", pattern=b"pat", fail_pattern=None)
    assert ec.cmd == b"test"
    assert ec.pattern == b"pat"
    assert ec.fail_pattern is None

    ec2 = EncodedCommand(cmd=b"a", pattern=b"b", fail_pattern=b"c")
    assert ec2.fail_pattern == b"c"
    assert ec2 == EncodedCommand(b"a", b"b", b"c")


def test_prepare_command(builder: CommandBuilder) -> None:
    assert builder._prepare_command("aaa", None) == "aaa"
    assert builder._prepare_command("aaa", "bbb") == "aaa bbb"
    assert builder._prepare_command("aaa", ["bbb", "ccc"]) == "aaa bbb ccc"
    assert builder._prepare_command("aaa", ("bbb", "ccc")) == "aaa bbb ccc"

    with pytest.raises(ValueError):
        builder._prepare_command("", None)

    with pytest.raises(ValueError):
        builder._prepare_command(None, None)  # type: ignore[arg-type]


def test_build_expect_pattern(builder: CommandBuilder) -> None:
    assert (
        builder._build_expect_pattern(["aaa", "bbb"], False, False)
        == "(aaa|bbb)"
    )
    assert (
        builder._build_expect_pattern(["aaa", "bbb"], True, False)
        == "^(?=.*aaa)(?=.*bbb)"
    )
    assert (
        builder._build_expect_pattern(["aaa", "bbb"], True, True)
        == "^(?=.*aaa)(?=.*bbb)"
    )
    assert (
        builder._build_expect_pattern(["aaa", "bbb"], False, True)
        == "(aaa|bbb)"
    )


def test_default_prompt_pattern(builder: CommandBuilder) -> None:
    # Uses stored prompt when flag is empty
    result = builder._default_prompt_pattern("test")
    assert "nsh" in result
    assert "(?!.*test)" in result

    # Uses flag when provided
    result = builder._default_prompt_pattern("cmd", flag="PROMPT>")
    assert "PROMPT" in result
    assert "(?!.*cmd)" in result

    # Newline command — no negative lookahead
    result = builder._default_prompt_pattern("\n")
    assert "(?!" not in result


def test_prepare_pattern_with_expects(builder: CommandBuilder) -> None:
    p = builder._prepare_pattern("cmd", ["OK"], "", True, False)
    assert re.search(p, "OK")
    assert re.search(p, "cmd: command not found")

    p2 = builder._prepare_pattern("cmd", ["A", "B"], "", False, False)
    assert re.search(p2, "A")
    assert re.search(p2, "B")
    assert re.search(p2, "cmd: command not found")


def test_prepare_pattern_match_all_is_linear(builder: CommandBuilder) -> None:
    """A match_all pattern must not scan the buffer once per position."""
    p = builder._prepare_pattern(
        "popen", ["Calling pclose()"], "", True, False
    )
    # a device dumping thousands of builtin names before the expected line
    buf = "    ltp_some_test_case_name_padded_to_width\n" * 5000
    assert len(buf) > 200000

    t0 = time.time()
    assert re.search(p, buf) is None
    assert time.time() - t0 < 0.5

    assert re.search(p, buf + "Calling pclose()\n")
    assert re.search(p, buf + "popen: command not found\n")

    p2 = builder._prepare_pattern("cmd", ["A", "B"], "", True, False)
    assert re.search(p2, buf + "B\n" + buf + "A\n")
    assert re.search(p2, buf + "A\n") is None


def test_prepare_pattern_without_expects(builder: CommandBuilder) -> None:
    p = builder._prepare_pattern("cmd", None, "", True, False)
    assert re.search(p, "nsh> ")
    assert re.search(p, "cmd: command not found")
    assert not re.search(p, "nsh> cmd")

    p2 = builder._prepare_pattern("cmd", None, "MY>", True, False)
    assert re.search(p2, "MY>")
    assert not re.search(p2, "MY> cmd")


def test_encode_for_device(builder: CommandBuilder) -> None:
    assert builder._encode_for_device("aaa", ["bbb", "ccc"]) == (
        b"aaa",
        b"bbbccc",
    )
    assert builder._encode_for_device("aaa", [b"bbb", b"ccc"]) == (
        b"aaa",
        b"bbbccc",
    )
    assert builder._encode_for_device("aaa", "bbb") == (b"aaa", b"bbb")
    assert builder._encode_for_device("aaa", b"bbb") == (b"aaa", b"bbb")
    assert builder._encode_for_device("aaa", bytearray(b"bbb")) == (
        b"aaa",
        b"bbb",
    )


def test_build_fail_pattern_bytes(builder: CommandBuilder) -> None:
    assert builder._build_fail_pattern_bytes("ERROR", False) == b"(?:ERROR)"
    assert builder._build_fail_pattern_bytes("err.+", True) == b"(?:err.+)"
    assert (
        builder._build_fail_pattern_bytes(["ERR", "PANIC"], False)
        == b"(?:ERR)|(?:PANIC)"
    )
    assert (
        builder._build_fail_pattern_bytes(r"err\d+", False) == rb"(?:err\\d\+)"
    )


def test_encode_fail_pattern(builder: CommandBuilder) -> None:
    assert builder._encode_fail_pattern("ERROR") == b"(?:ERROR)"
    assert builder._encode_fail_pattern(b"PANIC") == b"(?:PANIC)"
    assert (
        builder._encode_fail_pattern(["ERR", b"CRASH"]) == b"(?:ERR)|(?:CRASH)"
    )


def test_build_no_expects_no_fail(builder: CommandBuilder) -> None:
    encoded = builder.build("test", None, None, "", True, False, None)
    assert encoded.cmd == b"test"
    assert b"nsh" in encoded.pattern
    assert encoded.fail_pattern is None


def test_build_with_expects_and_fail(builder: CommandBuilder) -> None:
    encoded = builder.build("test", ["OK"], None, "", True, False, "ERROR")
    assert encoded.cmd == b"test"
    assert b"OK" in encoded.pattern
    assert encoded.fail_pattern == b"(?:ERROR)"


def test_build_with_args(builder: CommandBuilder) -> None:
    encoded = builder.build("ls", None, ["-la"], "", True, False, None)
    assert encoded.cmd == b"ls -la"


def test_build_empty_cmd_raises(builder: CommandBuilder) -> None:
    with pytest.raises(ValueError):
        builder.build("", None, None, "", True, False, None)


def test_build_raw_explicit_pattern(builder: CommandBuilder) -> None:
    encoded = builder.build_raw("test", "pattern", None, None)
    assert encoded.cmd == b"test"
    assert encoded.pattern == b"pattern"
    assert encoded.fail_pattern is None


def test_build_raw_default_pattern(builder: CommandBuilder) -> None:
    encoded = builder.build_raw("test", None, None, None)
    assert encoded.cmd == b"test"
    assert b"nsh" in encoded.pattern
    assert encoded.fail_pattern is None


def test_build_raw_with_fail(builder: CommandBuilder) -> None:
    encoded = builder.build_raw("test", "pat", None, "ERROR")
    assert encoded.fail_pattern == b"(?:ERROR)"

    encoded2 = builder.build_raw("test", "pat", None, b"PANIC")
    assert encoded2.fail_pattern == b"(?:PANIC)"

    encoded3 = builder.build_raw("test", "pat", None, ["ERR", b"CRASH"])
    assert encoded3.fail_pattern == b"(?:ERR)|(?:CRASH)"


def test_build_raw_empty_cmd_raises(builder: CommandBuilder) -> None:
    with pytest.raises(ValueError):
        builder.build_raw("", "pat", None, None)


def test_encode_pattern(builder: CommandBuilder) -> None:
    assert builder.encode_pattern("PASS") == b"PASS"
    assert builder.encode_pattern(b"PASS") == b"PASS"
    assert builder.encode_pattern(["OK", b"DONE"]) == b"OKDONE"


def test_encode_fail_pattern_public(builder: CommandBuilder) -> None:
    assert builder.encode_fail_pattern("FAIL") == b"(?:FAIL)"
    assert (
        builder.encode_fail_pattern(["ERR", b"CRASH"]) == b"(?:ERR)|(?:CRASH)"
    )
