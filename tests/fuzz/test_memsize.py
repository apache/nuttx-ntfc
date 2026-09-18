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

from unittest.mock import MagicMock, patch

from ntfc.fuzz import memsize


def test_elf_size_parses_size_output():
    out = (
        "   text\t   data\t    bss\t    dec\t    hex\tfilename\n"
        "  10000\t    200\t    500\t  10700\t   29cc\tnuttx\n"
    )
    with patch(
        "subprocess.run", return_value=MagicMock(stdout=out, returncode=0)
    ):
        assert memsize.elf_size("nuttx") == (10000, 200, 500)


def test_elf_size_returns_zeros_on_failure():
    with patch(
        "subprocess.run", return_value=MagicMock(stdout="", returncode=1)
    ):
        assert memsize.elf_size("nuttx") == (0, 0, 0)


def test_elf_size_returns_zeros_on_oserror():
    with patch("subprocess.run", side_effect=OSError):
        assert memsize.elf_size("nuttx") == (0, 0, 0)


def test_elf_size_returns_zeros_on_short_output():
    with patch(
        "subprocess.run",
        return_value=MagicMock(stdout="only a header line\n", returncode=0),
    ):
        assert memsize.elf_size("nuttx") == (0, 0, 0)


def test_elf_size_returns_zeros_on_unparseable_row():
    out = "text data bss\nnot numbers here really\n"
    with patch(
        "subprocess.run", return_value=MagicMock(stdout=out, returncode=0)
    ):
        assert memsize.elf_size("nuttx") == (0, 0, 0)


def test_footprint():
    assert memsize.footprint(10000, 200, 500) == (10200, 700)
