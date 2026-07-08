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
from dummydev import DeviceDummy

from ntfc.envconfig import EnvConfig

pytest_plugins = ["pytester"]


@pytest.fixture
def config_dummy():
    conf_dir = {
        "config": {},
        "product": {
            "name": "product-dummy",
            "cores": {
                "core0": {
                    "name": "dummy",
                    "device": "sim",
                    "elf_path": "",
                    "uptime": 1,
                }
            },
        },
    }
    return conf_dir


@pytest.fixture
def config_sim():
    conf_dir = {
        "config": {},
        "product": {
            "name": "product-sim",
            "cores": {
                "core0": {
                    "name": "sim",
                    "device": "sim",
                    "elf_path": "./tests/resources/nuttx/sim/nuttx",
                    "conf_path": "./tests/resources/nuttx/sim/kv_config",
                    "uptime": 1,
                }
            },
        },
    }
    return conf_dir


@pytest.fixture
def envconfig_dummy(config_dummy):
    return EnvConfig(config_dummy)


@pytest.fixture
def config_smp_dummy():
    """SMP configuration with multiple cores sharing one device."""
    conf_dir = {
        "config": {},
        "product": {
            "name": "product-smp",
            "platform": "smp",
            "cores": {
                "core0": {
                    "name": "main",
                    "device": "sim",
                    "elf_path": "",
                    "uptime": 1,
                },
                "core1": {
                    "name": "cpu1",
                    "device": "sim",
                    "elf_path": "",
                    "uptime": 1,
                },
            },
        },
    }
    return conf_dir


@pytest.fixture
def envconfig_smp_dummy(config_smp_dummy):
    """SMP EnvConfig for testing multi-core SMP mode."""
    return EnvConfig(config_smp_dummy)


@pytest.fixture
def device_dummy(config_dummy):

    dev = DeviceDummy(config_dummy)
    return dev
