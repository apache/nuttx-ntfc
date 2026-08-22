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

from typing import TYPE_CHECKING

from .linux import DeviceLinux
from .nuttx import DeviceNuttx

if TYPE_CHECKING:
    from ntfc.coreconfig import CoreConfig

    from .oscommon import OSCommon

###############################################################################
# Function: get_device
###############################################################################


def get_os(conf: "CoreConfig") -> "OSCommon":
    """Get OS abstraction."""
    operating_systems = {
        "linux": DeviceLinux,
        "nuttx": DeviceNuttx,
    }
    factory = operating_systems.get(conf.os)
    if factory is None:
        raise ValueError(f"unsupported operating system: {conf.os}")
    return factory(conf)
