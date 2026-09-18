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

"""Data model shared across the fuzz modules."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class SymbolInfo:
    """A fuzzable Kconfig symbol discovered for a base configuration."""

    name: str  # symbol name without the CONFIG_ prefix
    kind: str  # "bool" (only bool is fuzzed in this version)
    cur_value: str  # value in the expanded base config ("n", "y", ...)
    target: str  # value the candidate sets it to ("y")
    files: List[str] = field(default_factory=list)  # defining Kconfig files
    in_choice: bool = False  # member of a choice block

    def to_dict(self) -> Dict[str, Any]:
        """Return the symbol as a plain dictionary."""
        return asdict(self)
