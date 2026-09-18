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

from unittest.mock import patch

from click.testing import CliRunner

from ntfc.cli.main import main

CAMP = "tests/fuzz/resources/campaign-build.yaml"
TARGET = "tests/fuzz/resources/target-sim.yaml"


def test_fuzz_command_invokes_engine():
    runner = CliRunner()
    with patch("ntfc.cli.main.fuzz_run", return_value=0) as fr:
        result = runner.invoke(main, ["fuzz", "--campaign", CAMP])
    assert result.exit_code == 0
    assert fr.called
    ctx = fr.call_args[0][0]
    assert ctx.runfuzz is True
    assert ctx.fuzzpath == CAMP


def test_fuzz_command_nonzero_exits():
    runner = CliRunner()
    with patch("ntfc.cli.main.fuzz_run", return_value=1):
        result = runner.invoke(main, ["fuzz", "--campaign", CAMP])
    assert result.exit_code == 1


def test_fuzz_command_passes_confpath_and_list():
    runner = CliRunner()
    with patch("ntfc.cli.main.fuzz_run", return_value=0) as fr:
        result = runner.invoke(
            main,
            ["fuzz", "--campaign", CAMP, "--list", "--confpath", TARGET],
        )
    assert result.exit_code == 0
    ctx = fr.call_args[0][0]
    assert ctx.fuzz_list is True
    assert ctx.fuzz_confpath == TARGET


def test_fuzz_command_requires_campaign():
    runner = CliRunner()
    result = runner.invoke(main, ["fuzz"])
    assert result.exit_code != 0
