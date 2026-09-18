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

"""Module containing the Click environment."""

from dataclasses import dataclass
from typing import Any, List, Optional

import click

###############################################################################
# Class: DEnvironmentData
###############################################################################


@dataclass
class DEnvironmentData:
    """Environment data."""

    # common flags
    helpnow: bool = False
    debug: bool = False
    verbose: bool = False

    # commands to run
    runcollect: bool = False
    runtest: bool = False
    runbuild: bool = False

    # commands options
    rebuild: bool = False
    exitonfail: bool = False
    flash: bool = False
    nologs: bool = False
    list_tests: bool = False
    list_modules: bool = False
    collect_only: bool = False
    loops: int = 1
    collect: Optional[str] = None
    result: Optional[Any] = None
    modules: Optional[List[str]] = None
    select_individual_tests: Optional[List[int]] = None

    # multi-session
    runmulti: bool = False
    manifest: Optional[str] = None

    # fuzzing
    runfuzz: bool = False
    fuzzpath: Optional[str] = None
    fuzz_confpath: Optional[str] = None
    fuzz_list: bool = False
    fuzz_dry_run: bool = False

    # files
    testpath: Optional[str] = None
    confpath: Optional[str] = None
    jsonconf: Optional[str] = None


###############################################################################
# Class: Environment
###############################################################################


class Environment(DEnvironmentData):
    """A class with application environment."""

    def __init__(self) -> None:
        """Initialize environment."""
        super().__init__()


###############################################################################
# Decorator: pass_environment
###############################################################################


# custom environment decorator
pass_environment = click.make_pass_decorator(Environment, ensure=True)
