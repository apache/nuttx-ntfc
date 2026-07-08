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

from ntfc.productconfig import ProductConfig


def test_product_config():

    conf = {
        "name": "product",
        "cores": {
            "core0": {
                "name": "dummy",
                "device": "sim",
                "elf_path": "./tests/resources/nuttx/sim/nuttx",
                "conf_path": "./tests/resources/nuttx/sim/kv_config",
                "uptime": 1,
            },
            "core1": {
                "name": "dummy2",
                "device": "sim2",
                "elf_path": "./tests/resources/nuttx/sim/nuttx",
                "conf_path": "./tests/resources/nuttx/sim/kv_config",
                "uptime": 1,
            },
        },
    }

    p = ProductConfig(conf)

    assert p.core(0)["name"] == "dummy"
    assert p.core(0)["device"] == "sim"
    assert p.core(1)["name"] == "dummy2"
    assert p.core(1)["device"] == "sim2"

    with pytest.raises(AttributeError):
        p.cmd_check("aaa", 3)

    with pytest.raises(AttributeError):
        p.kv_check("aaa", 3)

    assert p.kv_check("aaa", 0) is False
    assert p.kv_check("aaa", 1) is False
    assert p.kv_check("CONFIG_SYSTEM_NSH", 0) is True
    assert p.kv_check("CONFIG_SYSTEM_NSH", 1) is True

    assert p.cmd_check("aaa", 0) is False
    assert p.cmd_check("aaa", 1) is False
    assert p.cmd_check("hello_main", 0) is True
    assert p.cmd_check("hello_main", 1) is True

    conf = {
        "name": "product",
    }

    p = ProductConfig(conf)

    assert p.cores == {}
    with pytest.raises(AttributeError):
        p.key_check("aaa")
    with pytest.raises(AttributeError):
        p.cmd_check("aaa")
    with pytest.raises(AttributeError):
        p.kv_check("aaa")


def test_product_config_core_parsing():
    """Test ProductConfig with various core configurations."""

    # Test with invalid core keys (should be skipped)
    conf = {
        "name": "product",
        "cores": {
            "core0": {"name": "main", "device": "sim"},
            "invalid_key": {"name": "should_be_skipped"},
            "core1": {"name": "cpu1", "device": "sim"},
        },
    }
    p = ProductConfig(conf)
    assert p.cores_num == 2
    assert "main" in p.core_names
    assert "cpu1" in p.core_names

    # Test with empty name (should auto-generate)
    conf = {
        "name": "product",
        "cores": {
            "core0": {"device": "sim"},  # Empty name -> "main"
            "core1": {"device": "sim"},  # Empty name -> "cpu1"
            "core2": {"device": "sim"},  # Empty name -> "cpu2"
        },
    }
    p = ProductConfig(conf)
    assert p.core_names == ["main", "cpu1", "cpu2"]

    # Test with invalid core key format (should skip)
    conf = {
        "name": "product",
        "cores": {
            "core0": {"name": "main", "device": "sim"},
            "core_invalid": {"device": "sim"},  # Invalid format
        },
    }
    p = ProductConfig(conf)
    assert p.cores_num == 1
    assert p.core_names == ["main"]


def test_product_config_get_core_name():
    """Test _get_core_name method with various inputs."""

    # Test with string input (should return as-is)
    conf = {
        "name": "product",
        "cores": {
            "core0": {"name": "main", "device": "sim"},
            "core1": {"name": "cpu1", "device": "sim"},
        },
    }
    p = ProductConfig(conf)
    assert p._get_core_name("main") == "main"
    assert p._get_core_name("cpu1") == "cpu1"

    # Test with invalid type
    conf = {
        "name": "product",
        "cores": {"core0": {"name": "main", "device": "sim"}},
    }
    p = ProductConfig(conf)
    with pytest.raises(TypeError):
        p._get_core_name([1, 2, 3])
    with pytest.raises(TypeError):
        p._get_core_name(None)

    # Test with invalid cores format (coreX raises ValueError,
    # should find core1)
    conf = {
        "name": "product",
        "cores": {
            "coreX": {"name": "invalid", "device": "sim"},
            "core1": {"name": "cpu1", "device": "sim"},
        },
    }
    p = ProductConfig(conf)
    assert p._get_core_name(1) == "cpu1"

    # Test with non-core keys (should skip invalid_key and find core1)
    conf = {
        "name": "product",
        "cores": {
            "invalid_key": {"name": "should_be_skipped"},
            "core1": {"name": "cpu1", "device": "sim"},
        },
    }
    p = ProductConfig(conf)
    assert p._get_core_name(1) == "cpu1"


def test_product_config_core_names_property():
    """Test core_names property."""

    conf = {
        "name": "product",
        "cores": {
            "core0": {"name": "main", "device": "sim"},
            "core1": {"name": "cpu1", "device": "sim"},
            "core2": {"name": "cpu2", "device": "sim"},
        },
    }

    p = ProductConfig(conf)
    assert p.core_names == ["main", "cpu1", "cpu2"]


def test_product_config_active_cores():
    conf = {
        "name": "product",
        "cores": {
            "core0": {"name": "cpuapp", "device": "sim"},
            "core1": {
                "name": "cpunet",
                "device": "sim",
                "flash_only": True,
            },
            "core2": {"name": "sensor", "device": "sim"},
        },
    }

    p = ProductConfig(conf)
    assert p.core_names == ["cpuapp", "cpunet", "sensor"]
    assert p.active_core_indices == [0, 2]
    assert p.active_core_names == ["cpuapp", "sensor"]
    assert p.active_cores_num == 2
    assert p.primary_test_core_index == 0


def test_product_config_cfg_core():
    """Test cfg_core and cfg_core_by_name methods."""

    conf = {
        "name": "product",
        "cores": {
            "core0": {"name": "main", "device": "sim"},
            "core1": {"name": "cpu1", "device": "sim"},
        },
    }

    p = ProductConfig(conf)

    # Test cfg_core_by_name with valid names
    core0 = p.cfg_core_by_name("main")
    assert core0 is not None
    assert core0._config["name"] == "main"

    core1 = p.cfg_core_by_name("cpu1")
    assert core1 is not None
    assert core1._config["name"] == "cpu1"

    # Test cfg_core_by_name with invalid name
    with pytest.raises(AttributeError, match="no data for core 'invalid'"):
        p.cfg_core_by_name("invalid")

    # Test cfg_core with invalid index
    with pytest.raises(AttributeError, match="no data for core index 5"):
        p.cfg_core(5)


def test_product_config_debug_defaults():
    """Test debug property defaults when the section is absent."""

    conf = {
        "name": "product",
        "cores": {"core0": {"name": "main", "device": "sim"}},
    }

    p = ProductConfig(conf)
    assert p.debug.coredump.enable is False
    assert p.debug.coredump.collection_type == "auto"
    assert p.debug.gdb.enable is False


def test_product_config_debug_parsing():
    """Test debug property with a full debug section."""

    conf = {
        "name": "product",
        "cores": {"core0": {"name": "main", "device": "sim"}},
        "debug": {
            "coredump": {"enable": True, "type": "gdb", "limit": 3},
            "gdb": {"enable": True, "target": "localhost:1234"},
            "fastboot": {"dev_sn": "ABC123"},
            "ymodem": {"serial_port": "/dev/ttyUSB0"},
        },
    }

    p = ProductConfig(conf)
    assert p.debug.coredump.enable is True
    assert p.debug.coredump.collection_type == "gdb"
    assert p.debug.coredump.limit == 3
    assert p.debug.gdb.enable is True
    assert p.debug.gdb.target == "localhost:1234"
    assert p.debug.fastboot.dev_sn == "ABC123"
    assert p.debug.ymodem.serial_port == "/dev/ttyUSB0"


def test_product_config_debug_invalid():
    """Test that an invalid coredump type raises ValueError."""

    conf = {
        "name": "product",
        "cores": {"core0": {"name": "main", "device": "sim"}},
        "debug": {"coredump": {"type": "bogus"}},
    }

    with pytest.raises(ValueError):
        ProductConfig(conf)


def test_product_config_platform_properties():
    """Test platform, is_smp, and is_amp properties."""

    # Test with AMP platform (default)
    conf_amp = {
        "name": "product",
        "platform": "amp",
        "cores": {"core0": {"name": "main", "device": "sim"}},
    }

    p_amp = ProductConfig(conf_amp)
    assert p_amp.platform == "amp"
    assert p_amp.is_amp is True
    assert p_amp.is_smp is False

    # Test with SMP platform
    conf_smp = {
        "name": "product",
        "platform": "smp",
        "cores": {"core0": {"name": "main", "device": "sim"}},
    }

    p_smp = ProductConfig(conf_smp)
    assert p_smp.platform == "smp"
    assert p_smp.is_smp is True
    assert p_smp.is_amp is False
