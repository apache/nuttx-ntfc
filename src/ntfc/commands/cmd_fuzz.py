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

"""Module containing NTFC fuzz command."""

from typing import Optional

import click

from ntfc.cli.environment import Environment, pass_environment

###############################################################################
# Command: cmd_fuzz
###############################################################################


@click.command(name="fuzz")
@click.option(
    "--campaign",
    required=True,
    type=click.Path(resolve_path=False),
    help="Path to a fuzz config YAML file (what to fuzz).",
)
@click.option(
    "--confpath",
    default=None,
    type=click.Path(resolve_path=False),
    help="NTFC target config (device/board). Required for the ostest feature; "
    "ignored for build/mem, which build the fuzz config's own board/tree.",
)
@click.option(
    "--list",
    "list_surface",
    is_flag=True,
    help="Only discover and print the fuzz surface; do not build.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the planned candidate matrix without building.",
)
@pass_environment
def cmd_fuzz(
    ctx: Environment,
    campaign: str,
    confpath: Optional[str],
    list_surface: bool,
    dry_run: bool,
) -> bool:
    """Run a Kconfig fuzzing campaign (build / ostest / mem)."""
    ctx.runfuzz = True
    ctx.fuzzpath = campaign
    ctx.fuzz_confpath = confpath
    ctx.fuzz_list = list_surface
    ctx.fuzz_dry_run = dry_run

    return True
