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


@pytest.mark.dep_config("CONFIG_EXAMPLES_HELLO")
def test_test4_simple_1():  # pragma: no cover
    assert True


@pytest.mark.dep_config("CONFIG_XXXXX")
def test_test4_simple_2():  # pragma: no cover
    assert True


@pytest.mark.cmd_check("hello_main")
def test_test4_simple_3():  # pragma: no cover
    assert True


@pytest.mark.cmd_check("xxxx_main")
def test_test4_simple_4():  # pragma: no cover
    assert True


@pytest.mark.extra_opts("xxxx")
def test_test4_simple_5():  # pragma: no cover
    assert True
