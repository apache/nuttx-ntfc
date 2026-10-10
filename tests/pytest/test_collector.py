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

from ntfc.pytest.collector import CollectorPlugin
from ntfc.pytest.mypytest import MyPytest


def test_collectorplugin(config_dummy):

    _ = CollectorPlugin(config_dummy)


def test_runner_module_order(config_sim, device_dummy):
    with patch("ntfc.cores.get_device", return_value=device_dummy):
        # Order:
        # test_Test2: 1 (start)
        # test_Test3_Test4: -1 (end)
        # test_Test1: unspecified (middle)
        jsoncfg = {
            "module": {
                "order": [
                    {"module": "test_Test2", "value": "1"},
                    {"module": "test_Test3_Test4", "value": "-1"},
                ]
            }
        }

        p = MyPytest(config_sim, confjson=jsoncfg)
        path = "./tests/resources/tests_dirs"
        col = p.collect(path)

        # Total 8 items: 4 from test2, 2 from test1, 2 from test3/test4
        assert len(col.items) == 8

        # Verify order
        # test_Test2 (v=1) should be at the beginning
        for i in range(4):
            assert col.items[i].module2 == "test_Test2"

        # test_Test1 (unspecified) should be in the middle
        for i in range(4, 6):
            assert col.items[i].module2 == "test_Test1"

        # test_Test3_Test4 (v=-1) should be at the end
        for i in range(6, 8):
            assert col.items[i].module2 == "test_Test3_Test4"


def test_runner_module_exclude(config_sim, device_dummy):
    with patch("ntfc.cores.get_device", return_value=device_dummy):
        jsoncfg = {
            "module": {
                "exclude_module": ["test_Test1"],
            }
        }

        p = MyPytest(config_sim, confjson=jsoncfg)
        path = "./tests/resources/tests_dirs"
        col = p.collect(path)

        # 8 total - 2 from test1 = 6 items
        assert len(col.items) == 6
        for item in col.items:
            assert item.module2 != "test_Test1"


def test_runner_test_exclude(config_sim, device_dummy):
    with patch("ntfc.cores.get_device", return_value=device_dummy):
        jsoncfg = {
            "module": {
                "exclude_test": ["test_test2_simple_1"],
            }
        }

        p = MyPytest(config_sim, confjson=jsoncfg)
        path = "./tests/resources/tests_dirs"
        col = p.collect(path)

        # 8 total - 1 excluded by name = 7 items
        assert len(col.items) == 7
        for item in col.items:
            assert item.name != "test_test2_simple_1"

        skipped = {item.name: reason for item, reason in col.skipped}
        assert skipped == {"test_test2_simple_1": "excluded test"}


def test_runner_module_order_complex(config_sim, device_dummy):
    with patch("ntfc.cores.get_device", return_value=device_dummy):
        # Multiple positive and negative values
        jsoncfg = {
            "module": {
                "order": [
                    {"module": "test_Test2", "value": "2"},
                    {"module": "test_Test1", "value": "1"},
                    {"module": "test_Test3_Test4", "value": "-1"},
                ]
            }
        }

        p = MyPytest(config_sim, confjson=jsoncfg)
        path = "./tests/resources/tests_dirs"
        col = p.collect(path)

        # test_Test1 (v=1) comes first (2 items)
        assert col.items[0].module2 == "test_Test1"
        # test_Test2 (v=2) comes next (4 items)
        assert col.items[2].module2 == "test_Test2"
        # test_Test3_Test4 (v=-1) comes last (2 items)
        assert col.items[6].module2 == "test_Test3_Test4"
