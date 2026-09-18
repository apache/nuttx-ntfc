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

import pytest


@pytest.fixture(autouse=True)
def _isolated_build_root(tmp_path, monkeypatch):
    """Keep engine tests away from the repo's real ./build directory.

    The engines rmtree their per-candidate build dirs; without this, a test
    run would delete directories of a real fuzz sweep happening in the same
    checkout (the campaign resources use the default ``./build``).
    """
    monkeypatch.setattr(
        "ntfc.fuzz.engine._build_root",
        lambda build_dir: str(tmp_path / "fuzz"),
    )
