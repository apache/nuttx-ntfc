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

import pytest

from ntfc.cores import CoresHandler
from ntfc.device.common import CmdReturn, CmdStatus


def test_cores_init(envconfig_dummy):

    with pytest.raises(TypeError):
        _ = CoresHandler(None)

    with patch("ntfc.core.ProductCore") as mockdevice:

        c0 = mockdevice.return_value
        c = CoresHandler(envconfig_dummy.product[0])
        c._cores[0] = c0

        c.core(0).sendCommand.return_value = 0
        assert c.sendCommand("") == 0
        c.core(0).sendCommand.return_value = 1
        assert c.sendCommand("") == 1

        c.core(0).sendCommandReadUntilPattern.return_value = CmdReturn(
            CmdStatus.SUCCESS
        )
        assert c.sendCommandReadUntilPattern("") == CmdReturn(
            CmdStatus.SUCCESS
        )

        c.core(0).sendCommandReadUntilPattern.return_value = CmdReturn(
            CmdStatus.TIMEOUT
        )
        assert c.sendCommandReadUntilPattern("") == CmdReturn(
            CmdStatus.TIMEOUT
        )

        c.core(0).readUntilPattern.return_value = CmdReturn(CmdStatus.SUCCESS)
        assert c.readUntilPattern("pattern") == CmdReturn(CmdStatus.SUCCESS)

        c.core(0).readUntilPattern.return_value = CmdReturn(CmdStatus.FAILED)
        assert c.readUntilPattern("pattern") == CmdReturn(CmdStatus.FAILED)

        assert c.sendCtrlCmd("Z") is None

        c.core(0).busyloop = False
        assert c.busyloop is False
        c.core(0).busyloop = True
        assert c.busyloop is True

        c.core(0).flood = False
        assert c.flood is False
        c.core(0).flood = True
        assert c.flood is True

        c.core(0).crash = False
        assert c.crash is False
        c.core(0).crash = True
        assert c.crash is True

        c.core(0).notalive = False
        assert c.notalive is False
        c.core(0).notalive = True
        assert c.notalive is True

        c.core(0).reboot.return_value = False
        assert c.reboot() is True
        c.core(0).reboot.return_value = True
        assert c.reboot() is True

        with patch("ntfc.cores.run_parallel") as mock_parallel:
            mock_parallel.return_value = [False]
            assert c.force_panic() is True

        with patch("ntfc.cores.run_parallel") as mock_parallel:
            mock_parallel.return_value = [True]
            assert c.force_panic() is True


def test_cores_skip_flash_only_amp_core():
    conf = {
        "name": "product",
        "platform": "amp",
        "cores": {
            "core0": {"name": "cpuapp", "device": "sim"},
            "core1": {
                "name": "cpunet",
                "device": "sim",
                "flash_only": True,
            },
        },
    }

    from ntfc.productconfig import ProductConfig

    with (
        patch("ntfc.cores.get_device") as mock_get_device,
        patch("ntfc.cores.ProductCore") as mock_product_core,
    ):
        core = mock_product_core.return_value
        core.name = "cpuapp"
        mock_get_device.return_value = object()
        c = CoresHandler(ProductConfig(conf))
        c._cores[0] = core
        assert c.cores == ["cpuapp"]
        assert mock_get_device.call_count == 1


def test_cores_smp_all_flash_only():
    """SMP product with only flash_only cores creates no core instances."""
    conf = {
        "name": "product",
        "platform": "smp",
        "cores": {
            "core0": {
                "name": "cpuapp",
                "device": "sim",
                "flash_only": True,
            },
        },
    }

    from ntfc.productconfig import ProductConfig

    with patch("ntfc.cores.get_device") as mock_get_device:
        c = CoresHandler(ProductConfig(conf))
        assert c.cores == []
        mock_get_device.assert_not_called()


def test_cores_smp_mode(envconfig_smp_dummy):
    """Test CoresHandler in SMP mode."""

    with patch("ntfc.core.ProductCore") as mock_product_core:
        c0 = mock_product_core.return_value
        c0.name = "main"
        c = CoresHandler(envconfig_smp_dummy.product[0])

        # Replace cores[0] with our mock (following the pattern
        # from test_cores_init)
        c._cores[0] = c0

        # In SMP mode, should have 2 cores
        assert len(c.cores) == 2

        # Test sendCommand in SMP mode (only executes on core0)
        c0.sendCommand.return_value = 0
        assert c.sendCommand("test") == 0
        c0.sendCommand.assert_called_once()

        # Test sendCommandReadUntilPattern in SMP mode
        c0.sendCommandReadUntilPattern.return_value = CmdReturn(
            CmdStatus.SUCCESS
        )
        result = c.sendCommandReadUntilPattern("test")
        assert result.status == CmdStatus.SUCCESS
        c0.sendCommandReadUntilPattern.assert_called_once()

        # Test readUntilPattern in SMP mode
        c0.readUntilPattern.return_value = CmdReturn(CmdStatus.SUCCESS)
        result = c.readUntilPattern("pattern")
        assert result.status == CmdStatus.SUCCESS
        c0.readUntilPattern.assert_called_once()
