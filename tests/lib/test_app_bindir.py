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

import shutil

import pytest

from ntfc.lib.elf.app_bindir import AppBinDir

ELF_MAGIC = b"\x7fELF" + b"\x00" * 12


@pytest.fixture
def bindir(tmp_path):
    path = tmp_path / "bin"
    path.mkdir()
    for name in ("init", "hello", "getprime", "sh"):
        (path / name).write_bytes(ELF_MAGIC)
    # non-ELF entries are not commands
    (path / "README").write_text("not an application")
    (path / "subdir").mkdir()
    return path


def test_app_bindir_commands(bindir):
    b = AppBinDir(str(bindir))
    assert b.commands == ["getprime", "hello", "init", "sh"]


def test_app_bindir_missing_dir(tmp_path):
    # neither the binaries nor the sibling debug directory exist
    b = AppBinDir(str(tmp_path / "nonexistent"))
    assert b.commands == []
    assert b.has_command("hello") is False
    assert b.has_symbol("hello_main") is False


def test_app_bindir_has_command(bindir):
    b = AppBinDir(str(bindir))

    # exact file name
    assert b.has_command("hello") is True
    assert b.has_command("free") is False

    # flat-mode symbol markers map to the file name
    assert b.has_command("hello_main") is True
    assert b.has_command("free_main") is False

    # alternatives
    assert b.has_command("free|hello") is True
    assert b.has_command("free|df") is False

    # regex
    assert b.has_command("get.*") is True
    assert b.has_command("xyz.*") is False


def test_app_bindir_has_symbol(bindir):
    # unstripped sim ELF stands in for a debug application binary
    debug = bindir.parent / "bin_debug"
    debug.mkdir()
    shutil.copy("./tests/resources/nuttx/sim/nuttx", debug / "sh")
    (debug / "README").write_text("skipped: not an ELF")

    b = AppBinDir(str(bindir), str(debug))
    assert b.has_symbol("hello_main") is True
    assert b.has_symbol("missing|hello_main") is True
    assert b.has_symbol("missing.*|hello_main") is True
    assert b.has_symbol("hello_.*") is True
    assert b.has_symbol("no_such_symbol_xyz") is False

    # the sibling bin_debug directory is the default
    assert AppBinDir(str(bindir)).has_symbol("hello_main") is True


def test_app_bindir_symbols_span_all_binaries(bindir):
    debug = bindir.parent / "bin_debug"
    debug.mkdir()
    for name in ("a", "b"):
        shutil.copy("./tests/resources/nuttx/sim/nuttx", debug / name)

    b = AppBinDir(str(bindir), str(debug))

    # every binary is read, not just the first one
    assert b.has_symbol("hello_main") is True
    assert b.has_symbol("no_such_symbol_xyz") is False
