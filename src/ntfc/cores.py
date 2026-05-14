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

"""Cores handler class implementation."""

from typing import (
    TYPE_CHECKING,
    Dict,
    List,
    Optional,
    Union,
    cast,
)

from ntfc.core import ProductCore
from ntfc.device.common import CmdReturn, CmdStatus
from ntfc.device.getdev import get_device
from ntfc.log.logger import logger

if TYPE_CHECKING:
    from ntfc.log.handler import LogHandler
    from ntfc.type_defs import PatternLike
from ntfc.parallel import run_parallel
from ntfc.productconfig import ProductConfig

###############################################################################
# Class: CoresHandler
###############################################################################


class CoresHandler:
    """This class implements work-around to run all cores at once.

    It can be useful to run tests for many DUT at once.
    Methods are executed in parallel using threads with result collection.
    """

    def __init__(self, conf: "ProductConfig") -> None:
        """Initialize all cores.

        :param conf: ProductConfig instance
        """
        if not isinstance(conf, ProductConfig):
            raise TypeError("Config instance is required")

        self._conf = conf
        self._cores: List[ProductCore] = []

        # For SMP mode, only create one device instance from the first active
        # core. For AMP mode, create separate device instances for active
        # cores.
        ignored = conf.ignored_cores
        active_cores = conf.active_core_indices
        if conf.is_smp:
            if not active_cores:
                return

            first_core = active_cores[0]
            dev = get_device(conf.cfg_core(first_core))
            self._cores.append(
                ProductCore(dev, conf.cfg_core(first_core), ignored)
            )

            for core in active_cores[1:]:
                self._cores.append(
                    ProductCore(dev, conf.cfg_core(core), ignored)
                )
        else:
            for core in active_cores:
                dev = get_device(conf.cfg_core(core))
                self._cores.append(
                    ProductCore(dev, conf.cfg_core(core), ignored)
                )

    def init(self) -> None:
        """Initialize all cores."""
        for core in self._cores:
            core.init()

    def start(self) -> None:
        """Start for all cores."""
        for core in self._cores:
            core.start()

    @property
    def cores(self) -> List[str]:
        """List of cores."""
        tmp = []
        for core in self._cores:
            tmp.append(core.name)
        return tmp

    def core(self, cpu: int = 0) -> ProductCore:
        """Get product core handler."""
        return self._cores[cpu]

    def sendCommand(  # noqa: N802
        self,
        cmd: str,
        expects: Optional[Union[str, List[str]]] = None,
        args: Optional[Union[str, List[str]]] = None,
        timeout: int = 30,
        flag: str = "",
        match_all: bool = True,
        regexp: bool = False,
    ) -> "CmdStatus":
        """Send command to all cores.

        In AMP mode: Execute in parallel on all cores.
        In SMP mode: Execute only on the current active core.
        Use switch_to_core() fixture to switch cores for multi-core.
        """
        if self._conf.is_smp:
            # SMP mode: Execute only on core0 (main core)
            # Use switch_to_core() fixture for multi-core testing
            return self._cores[0].sendCommand(
                cmd, expects, args, timeout, flag, match_all, regexp
            )
        else:
            # AMP mode: Execute in parallel on all cores
            results = run_parallel(
                self._cores,
                lambda c: c.sendCommand(
                    cmd, expects, args, timeout, flag, match_all, regexp
                ),
            )

            for idx, ret in enumerate(results):
                if ret != CmdStatus.SUCCESS:
                    logger.info(
                        f"sendCommand failed for core {self._cores[idx]}"
                    )
                    return cast("CmdStatus", ret)

            return CmdStatus.SUCCESS

    def sendCommandReadUntilPattern(  # noqa: N802
        self,
        cmd: str,
        pattern: "Optional[PatternLike]" = None,
        args: Optional[Union[str, List[str]]] = None,
        timeout: int = 30,
    ) -> "CmdReturn":
        """Send command to all cores.

        In AMP mode: Execute in parallel on all cores.
        In SMP mode: Execute only on the current active core.
        Use switch_to_core() fixture to switch cores for multi-core.
        """
        if self._conf.is_smp:
            # SMP mode: Execute only on core0 (main core)
            # Use switch_to_core() fixture for multi-core testing
            return self._cores[0].sendCommandReadUntilPattern(
                cmd, pattern, args, timeout
            )
        else:
            # AMP mode: Execute in parallel on all cores
            results = run_parallel(
                self._cores,
                lambda c: c.sendCommandReadUntilPattern(
                    cmd, pattern, args, timeout
                ),
            )

            for idx, ret in enumerate(results):
                if ret.status != CmdStatus.SUCCESS:
                    logger.info(
                        f"sendCommandReadUntilPattern failed for "
                        f"core {self._cores[idx]}"
                    )
                    return cast("CmdReturn", ret)

            return CmdReturn(CmdStatus.SUCCESS)

    def readUntilPattern(  # noqa: N802
        self,
        pattern: "PatternLike",
        timeout: int = 30,
        fail_pattern: "Optional[PatternLike]" = None,
    ) -> "CmdReturn":
        """Read device output until pattern without sending a command.

        In AMP mode: Execute in parallel on all cores.
        In SMP mode: Execute only on the current active core.
        Use switch_to_core() fixture to switch cores for multi-core.
        """
        if self._conf.is_smp:
            return self._cores[0].readUntilPattern(
                pattern, timeout, fail_pattern
            )
        else:
            results = run_parallel(
                self._cores,
                lambda c: c.readUntilPattern(pattern, timeout, fail_pattern),
            )

            for idx, ret in enumerate(results):
                if ret.status != CmdStatus.SUCCESS:
                    logger.info(
                        f"readUntilPattern failed for core {self._cores[idx]}"
                    )
                    return cast("CmdReturn", ret)

            return CmdReturn(CmdStatus.SUCCESS)

    def sendCtrlCmd(self, ctrl_char: str) -> None:  # noqa: N802
        """Send ctrl command to all cores in parallel."""
        run_parallel(self._cores, lambda c: c.sendCtrlCmd(ctrl_char))

    def reboot(self, timeout: int = 30) -> bool:
        """Run reboot for all cores in parallel."""
        results = run_parallel(self._cores, lambda c: c.reboot(timeout))
        for idx, result in enumerate(results):
            if not result:
                logger.info(f"reboot failed for core {self._cores[idx]}")
        return True

    def force_panic(self, timeout: int = 30) -> bool:
        """Force panic for all cores in parallel."""
        results = run_parallel(self._cores, lambda c: c.force_panic(timeout))
        for idx, result in enumerate(results):
            if not result:
                logger.info(f"force_panic failed for core {self._cores[idx]}")
        return True

    @property
    def busyloop(self) -> bool:
        """Get busyloop flag from cores in parallel."""
        results = run_parallel(self._cores, lambda c: c.busyloop)
        for idx, result in enumerate(results):
            if result:
                logger.info(f"busyloop for core {self._cores[idx]}")
                return True
        return False

    @property
    def flood(self) -> bool:
        """Get flood flag from cores in parallel."""
        results = run_parallel(self._cores, lambda c: c.flood)
        for idx, result in enumerate(results):
            if result:
                logger.info(f"flood for core {self._cores[idx]}")
                return True
        return False

    @property
    def crash(self) -> bool:
        """Get crash flag from cores in parallel."""
        results = run_parallel(self._cores, lambda c: c.crash)
        for idx, result in enumerate(results):
            if result:
                logger.info(f"crash for core {self._cores[idx]}")
                return True
        return False

    @property
    def notalive(self) -> bool:
        """Get notalive flag from cores in parallel."""
        results = run_parallel(self._cores, lambda c: c.notalive)
        for idx, result in enumerate(results):
            if result:
                logger.info(f"notalive for core {self._cores[idx]}")
                return True
        return False

    @property
    def cur_core(self) -> Optional[str]:
        """Call for all cores."""
        # REVISIT: how about this?
        return self.core(0).cur_core

    def start_log_collect(self, logs: "Dict[str, LogHandler]") -> None:
        """Start log collection for all cores in parallel."""
        run_parallel(self._cores, lambda c: c.start_log_collect(logs[c.name]))

    def stop_log_collect(self) -> None:
        """Stop log collection for all cores in parallel."""
        run_parallel(self._cores, lambda c: c.stop_log_collect())
