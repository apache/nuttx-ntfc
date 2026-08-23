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

"""Default commands."""

from typing import TYPE_CHECKING

from ntfc.commands.cmd_build import cmd_build
from ntfc.commands.cmd_collect import cmd_collect
from ntfc.commands.cmd_test import cmd_test
from ntfc.commands.cmd_usbsuspend import cmd_usbsuspend

if TYPE_CHECKING:
    import click

commands_list: list["click.Command"] = [
    cmd_build,
    cmd_collect,
    cmd_test,
    cmd_usbsuspend,
]
