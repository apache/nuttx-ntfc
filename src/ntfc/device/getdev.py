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

"""Get device from a given name."""

from typing import TYPE_CHECKING, Callable, Dict

from .netdev import DeviceNetdev
from .qemu import DeviceQemu
from .renode import DeviceRenode
from .serial import DeviceSerial
from .sim import DeviceSim

if TYPE_CHECKING:
    from ntfc.coreconfig import CoreConfig

    from .common import DeviceCommon


_DEVICE_FACTORIES: Dict[str, Callable[["CoreConfig"], "DeviceCommon"]] = {
    "sim": DeviceSim,
    "qemu": DeviceQemu,
    "serial": DeviceSerial,
    "renode": DeviceRenode,
    "netdev": DeviceNetdev,
}

###############################################################################
# Function: get_device
###############################################################################


def get_device(conf: "CoreConfig", cpu: int = 0) -> "DeviceCommon":
    """Get device from a given name."""
    devname = conf.device

    if not devname:
        raise ValueError("Unspecified device")

    factory = _DEVICE_FACTORIES.get(devname)
    if factory is None:
        raise ValueError("unsupported device")

    return factory(conf)
