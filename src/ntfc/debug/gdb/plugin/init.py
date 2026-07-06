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

"""NTFC GDB plugin loader.

This script is sourced by GDB (``gdb -ex "source init.py"``); it imports
all sibling plugin modules so their commands get registered.  GDB runs
sourced scripts with ``__name__ == "__main__"``.
"""

import importlib
import os
import sys
import traceback


def load() -> None:
    """Import all plugin modules located next to this file."""
    here = os.path.dirname(os.path.abspath(__file__))

    if here not in sys.path:
        sys.path.insert(0, here)

    self_name = os.path.basename(__file__)
    for file in sorted(os.listdir(here)):
        if not file.endswith(".py") or file == self_name:
            continue

        module_name = file[:-3]
        print(f"import {module_name}")
        try:
            importlib.import_module(module_name)
        except Exception:
            print(traceback.format_exc())

    print("NTFC GDB Plugin loaded Successfully")


if __name__ == "__main__":
    load()
