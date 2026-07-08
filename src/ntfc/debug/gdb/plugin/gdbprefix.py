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

"""Fail-fast GDB command wrapper loaded inside a GDB process.

Provides the ``ntfcgdbprefix`` command: it executes the wrapped command
and quits GDB when the command fails, so configuration errors are
detected immediately instead of leaving a half-configured debugger.
"""

import gdb


class NtfcGdbPrefix(gdb.Command):
    """Command ``ntfcgdbprefix``: execute a command, quit GDB on error.

    Usage: ``ntfcgdbprefix <gdb-command>``
    """

    def __init__(self) -> None:
        """Register the ``ntfcgdbprefix`` command."""
        super().__init__("ntfcgdbprefix", gdb.COMMAND_USER)

    def invoke(self, args: str, from_tty: bool) -> None:
        """Execute the wrapped command; quit GDB when it fails.

        :param args: The GDB command to execute.
        :param from_tty: ``True`` when invoked from an interactive tty.
        """
        try:
            gdb.execute(args)
            print(f"NTFC GDB cmd run successful: {args}")
        except gdb.error as e:
            print(f"NTFC GDB cmd run failed: {args}\n:{e}")
            gdb.execute("q")


NtfcGdbPrefix()
