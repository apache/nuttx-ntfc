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

from unittest.mock import MagicMock

import pytest
import yaml

from ntfc.envconfig import EnvConfig


def test_envconfig_common():

    conf = None
    with open("./tests/resources/nuttx/sim/config.yaml", "r") as f:
        conf = yaml.safe_load(f)

    env = EnvConfig(conf)

    # check device options
    assert env.common["cwd"] == "./"


def test_envconfig_product():

    with pytest.raises(TypeError):
        _ = EnvConfig(["1", "2"])

    conf = None
    with open("./tests/resources/nuttx/sim/config.yaml", "r") as f:
        conf = yaml.safe_load(f)

    env = EnvConfig(conf)

    assert env.core()["conf_path"] == "./tests/resources/nuttx/sim/kv_config"
    assert env.core()["elf_path"] == "./tests/resources/nuttx/sim/nuttx"

    assert (
        env.core(cpu=0)["conf_path"] == "./tests/resources/nuttx/sim/kv_config"
    )
    assert (
        env.core(cpu=1)["conf_path"] == "./tests/resources/nuttx/sim/kv_config"
    )

    with pytest.raises(KeyError):
        _ = env.core(cpu=2)["conf_path"]

    assert env.core(cpu=0)["elf_path"] == "./tests/resources/nuttx/sim/nuttx"
    assert env.core(cpu=1)["elf_path"] == "./tests/resources/nuttx/sim/nuttx"

    with pytest.raises(KeyError):
        _ = env.core(cpu=2)["elf_path"]

    assert env.core(cpu=0)["name"] == "main"
    assert env.core(cpu=1)["name"] == "core1"

    with pytest.raises(KeyError):
        _ = env.core(cpu=2)["name"]

    assert env.core(cpu=0)["device"] == "sim"
    assert env.core(cpu=1)["device"] == "sim"

    assert env.core(product=1)["name"] == "product1-main"
    assert env.core(product=1, cpu=0)["name"] == "product1-main"
    assert env.core(product=1, cpu=1)["name"] == "product1-core1"
    assert env.core(product=1, cpu=2) == {}
    assert env.core(product=1, cpu=3) == {}

    assert env.core(product=2)["name"] == "product2-main"
    assert env.core(product=2, cpu=0)["name"] == "product2-main"
    assert env.core(product=2, cpu=2) == {}
    assert env.core(product=2, cpu=3) == {}

    assert env.core(product=3, cpu=0) == {}
    assert env.core(product=3, cpu=1) == {}
    assert env.core(product=3, cpu=2) == {}
    assert env.core(product=3, cpu=3) == {}

    assert env.core(product=4, cpu=0) == {}
    assert env.core(product=4, cpu=1) == {}
    assert env.core(product=4, cpu=2) == {}
    assert env.core(product=4, cpu=3) == {}

    assert env.config is not None
    assert env.config["config"] is not None
    assert env.config["product"] is not None

    # check kconfig options
    assert env.kv_check("dummy") is False
    assert env.kv_check("CONFIG_ALLOW_BSD_COMPONENTS") is False
    assert env.kv_check("CONFIG_DEFAULT_SMALL") is False
    assert env.kv_check("CONFIG_HOST_LINUX") is True
    assert env.kv_check("CONFIG_APPS_DIR") == "../apps"
    assert env.kv_check("CONFIG_BASE_DEFCONFIG") == "sim/nsh"
    assert env.kv_check("CONFIG_BUILD_FLAT") is True

    # check available commands in elf
    assert env.cmd_check("dummy") is False
    assert env.cmd_check("dummy_main") is False
    assert env.cmd_check("dummy2_main") is False
    assert env.cmd_check("hello") is False
    assert env.cmd_check("hello_main") is True
    assert env.cmd_check("ostest") is False
    assert env.cmd_check("ostest_main") is True

    # get product
    assert env.product_get(0) is not None
    assert env.product_get(1) is not None
    assert env.product_get(2) is not None
    assert env.product_get(4) is None


def test_envconfig_extra_check(envconfig_dummy):
    """Test extra_check method for run_in_core option."""

    # Test with run_in_core in extra options
    assert envconfig_dummy.extra_check("run_in_core=cpu1") is True

    # Test without run_in_core
    assert envconfig_dummy.extra_check("some_other_option") is False

    # Test with empty string
    assert envconfig_dummy.extra_check("") is False


def test_envconfig_cmd_check_defaults_to_primary_test_core():
    env = EnvConfig({"config": {}, "product": {"name": "p0", "cores": {}}})
    product = MagicMock()
    product.primary_test_core_index = 2
    product.cmd_check.return_value = True
    product.kv_check.return_value = True
    env._products = [product]

    assert env.cmd_check("hello_main") is True
    assert env.kv_check("CONFIG_SYSTEM_NSH") is True
    product.cmd_check.assert_called_once_with("hello_main", 2)
    product.kv_check.assert_called_once_with("CONFIG_SYSTEM_NSH", 2)


def test_envconfig_cmd_check_respects_product_index():
    """cmd_check should use the requested product index."""
    env = EnvConfig({"config": {}, "product": {"name": "p0", "cores": {}}})
    p0 = MagicMock()
    p1 = MagicMock()
    p0.cmd_check.return_value = False
    p1.cmd_check.return_value = True
    p1.kv_check.return_value = True
    env._products = [p0, p1]

    assert env.cmd_check("hello_main", product=1, core=0) is True
    p1.cmd_check.assert_called_once_with("hello_main", 0)
    p0.cmd_check.assert_not_called()

    assert env.kv_check("CONFIG_SYSTEM_NSH", product=1, core=0) is True
    p1.kv_check.assert_called_once_with("CONFIG_SYSTEM_NSH", 0)
    p0.kv_check.assert_not_called()


def test_envconfig_recovery_defaults():
    """Test recovery property returns defaults when no config."""
    conf = None
    with open("./tests/resources/nuttx/sim/config.yaml", "r") as f:
        conf = yaml.safe_load(f)

    env = EnvConfig(conf)
    recovery = env.recovery
    assert recovery["max_retries"] == 3
    assert recovery["base_delay"] == 2.0
    assert recovery["reboot_timeout"] == 30


def test_envconfig_recovery_custom():
    """Test recovery property merges custom config."""
    conf = None
    with open("./tests/resources/nuttx/sim/config.yaml", "r") as f:
        conf = yaml.safe_load(f)

    conf.setdefault("config", {})["recovery"] = {
        "max_retries": 5,
        "base_delay": 1.0,
    }
    env = EnvConfig(conf)
    recovery = env.recovery
    assert recovery["max_retries"] == 5
    assert recovery["base_delay"] == 1.0
    assert recovery["reboot_timeout"] == 30  # default preserved
