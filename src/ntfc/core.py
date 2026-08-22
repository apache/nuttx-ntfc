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

"""Product core class implementation."""

import re
from enum import Enum as _Enum
from enum import auto
from typing import (
    TYPE_CHECKING,
    Any,
    List,
    Optional,
    Tuple,
    Union,
)

from ntfc.command_builder import CommandBuilder
from ntfc.coreconfig import CoreConfig
from ntfc.device.common import CmdReturn, CmdStatus
from ntfc.log.logger import logger

if TYPE_CHECKING:
    from ntfc.device.common import DeviceCommon
    from ntfc.log.handler import LogHandler
    from ntfc.type_defs import PatternLike

###############################################################################
# Enum: CoreStatus
###############################################################################


class CoreStatus(_Enum):
    """Core health status returned by :attr:`ProductCore.status`.

    :cvar NORMAL: Core is operating normally.
    :cvar CRASH: Core has crashed.
    :cvar BUSYLOOP: Core is stuck in a busy loop.
    :cvar FLOOD: Core is flooding output (stuck command).
    :cvar NOTALIVE: Core process/device is no longer alive.
    """

    NORMAL = auto()
    CRASH = auto()
    BUSYLOOP = auto()
    FLOOD = auto()
    NOTALIVE = auto()


###############################################################################
# Class: ProductCore
###############################################################################


class ProductCore:
    """This class implements product core under test."""

    def __init__(
        self,
        device: "DeviceCommon",
        conf: "CoreConfig",
        ignored_cores: Optional[List[str]] = None,
    ) -> None:
        """Initialize product core under test.

        :param device: DeviceCommon instance
        :param conf: CoreConfig instance
        :param ignored_cores: Core names to skip in :meth:`get_core_info`.
         Defaults to ``["dsp"]``.
        """
        if not device:
            raise TypeError("Device instance is required")

        if not isinstance(conf, CoreConfig):
            raise TypeError("Config instance is required")

        self._device = device
        self._uptime = conf.uptime
        self._name = conf.name
        self._conf = conf
        self._ignored_cores: List[str] = (
            list(ignored_cores) if ignored_cores is not None else ["dsp"]
        )
        self._builder = CommandBuilder(device.prompt, device.no_cmd)

        self._prompt = device.prompt
        self._main_prompt = self._prompt
        self._cur_prompt = self._main_prompt.decode("utf-8", errors="ignore")

        # cores info not ready yet, done in self.init() method called when
        # device is ready
        self._core0: Optional[str] = None
        self._cur_core: Optional[str] = None
        self._cores: Tuple[str, ...] = ()

    def __str__(self) -> str:
        """Get string for object."""
        return f"ProductCore: {self._name}"

    def _match_not_found(self, rematch: Optional[re.Match[Any]]) -> bool:
        """Check for 'command not found' message."""
        if not rematch:
            return False
        matched = rematch.group().strip()
        if isinstance(matched, (bytes, bytearray)):
            matched = matched.decode("utf-8", errors="ignore")
        return self._device.no_cmd in matched

    def sendCommand(  # noqa: N802
        self,
        cmd: str,
        expects: Optional[Union[str, List[str]]] = None,
        args: Optional[Union[str, List[str]]] = None,
        timeout: int = 30,
        flag: str = "",
        match_all: bool = True,
        regexp: bool = False,
        fail_pattern: Optional[Union[str, List[str]]] = None,
    ) -> "CmdStatus":
        """Send command and wait for expected response.

        :param cmd: Command to send
        :param expects: List of expected responses or None
        :param args: List of additional arguments to append to the command
         or None
        :param timeout: Timeout in seconds
        :param flag: Default _prompt
        :param match_all: "True" for all responses to match, "False" for any
         response to match
        :param regexp: "False" for str to match, "True" for regular
         expression to match
        :param fail_pattern: Pattern or list of patterns whose presence in the
         output immediately terminates the read and returns FAILED. Respects
         the ``regexp`` flag.
        :raises ValueError:
        :raises DeviceError: Communication error with device
        :raises TimeoutError: Response timeout

        :return: status : command execution status
        """
        encoded = self._builder.build(
            cmd, expects, args, flag, match_all, regexp, fail_pattern
        )

        logger.debug(
            f"Sending command: {encoded.cmd.decode()}, expecting: "
            f"{encoded.pattern.decode()} (timeout={timeout}s)"
        )

        cmdret = self._device.send_cmd_read_until_pattern(
            encoded.cmd,
            pattern=encoded.pattern,
            timeout=timeout,
            fail_pattern=encoded.fail_pattern,
        )

        if cmdret.valid_match() and self._match_not_found(cmdret.rematch):
            return CmdStatus.NOTFOUND

        return cmdret.status

    def sendCommandReadUntilPattern(  # noqa: N802
        self,
        cmd: str,
        pattern: "Optional[PatternLike]" = None,
        args: Optional[Union[str, List[str]]] = None,
        timeout: int = 30,
        fail_pattern: "Optional[PatternLike]" = None,
    ) -> CmdReturn:
        """Send command to device and read until a specific pattern.

        :param cmd: (str or list of strs) command to send to device
        :param pattern: (str, bytes, or list of (str, bytes)) String or regex
         pattern to look for. If a list, patterns will be concatenated
         with '.*'. The pattern will be converted to bytes for matching.
        :param args: List of additional arguments to append to the command
         or None
        :param timeout: (int) timeout value in seconds, default 30s.
        :param fail_pattern: (str, bytes, or list of (str, bytes)) Regex
         pattern or list of patterns whose presence in the output immediately
         terminates the read and returns FAILED.

        :return: CmdReturn : command return data
        """
        encoded = self._builder.build_raw(cmd, pattern, args, fail_pattern)

        logger.debug(
            f"Sending command: {encoded.cmd.decode()}, expecting pattern: "
            f"{encoded.pattern.decode()} (timeout={timeout}s)"
        )
        return self._device.send_cmd_read_until_pattern(
            encoded.cmd,
            pattern=encoded.pattern,
            timeout=timeout,
            fail_pattern=encoded.fail_pattern,
        )

    def readUntilPattern(  # noqa: N802
        self,
        pattern: "PatternLike",
        timeout: int = 30,
        fail_pattern: "Optional[PatternLike]" = None,
    ) -> CmdReturn:
        """Read device output until a pattern without sending a command.

        Useful for catching output from an already-running program and
        checking whether it passes or fails based on the patterns found.

        :param pattern: (str, bytes, or list of (str, bytes)) Regex pattern to
         wait for. Signals a successful outcome.
        :param timeout: (int) timeout value in seconds, default 30s.
        :param fail_pattern: (str, bytes, or list of (str, bytes)) Regex
         pattern or list of patterns whose presence in the output immediately
         terminates the read and returns FAILED.

        :return: CmdReturn : command return data
        """
        pattern_bytes = self._builder.encode_pattern(pattern)
        fail_pattern_bytes = (
            self._builder.encode_fail_pattern(fail_pattern)
            if fail_pattern
            else None
        )

        logger.debug(
            f"Reading until pattern: "
            f"{pattern.decode() if isinstance(pattern, bytes) else pattern} "
            f"(timeout={timeout}s)"
        )
        return self._device.read_until_pattern(
            pattern=pattern_bytes,
            timeout=timeout,
            fail_pattern=fail_pattern_bytes,
        )

    def sendCtrlCmd(self, ctrl_char: str) -> None:  # noqa: N802
        """Send a control character command (e.g., Ctrl+C).

        :param ctrl_char: Control character to send
        """
        if len(ctrl_char) != 1:
            raise ValueError(
                "ctrl_char must be a single alphabetic character."
            )

        if self._device.send_ctrl_cmd(ctrl_char) == CmdStatus.SUCCESS:
            logger.info(f"Successfully sent Ctrl+{ctrl_char}")
        else:
            logger.warning(f"Failed to send Ctrl+{ctrl_char}")

    # REVISIT: no proc/rpmsg in nuttx/upstream!
    def get_core_info(self) -> Tuple[str, ...]:
        """Retrieve CPU core information from the device.

        :return: Tuple containing Local CPU as first element followed by Remote
                 CPUs. Returns empty tuple on failure.
        """
        cmd_rpmsg = b"cat proc/rpmsg"
        timeout = 5

        # Send command and get raw output
        cmdret = self._device.send_cmd_read_until_pattern(
            cmd_rpmsg, pattern=self._main_prompt, timeout=timeout
        )

        if cmdret.status != 0:
            logger.error(f"Command failed with return code: {cmdret.status}")
            return ()

        # Parse output
        decoded_output = cmdret.output
        lines = [line.strip() for line in decoded_output.splitlines()]

        # Find header location
        header_index = next(
            (
                i
                for i, line in enumerate(lines)
                if "Local CPU" in line and "Remote CPU" in line
            ),
            -1,
        )

        # Early return if header not found
        if header_index == -1:
            logger.warning("CPU information header not found in output")
            return ()

        # Process data rows
        core_data = []
        for line in lines[header_index + 1 :]:  # pragma: no cover
            prompt = self._device.prompt.decode()
            if line.startswith(prompt):
                break  # Stop at next prompt

            parts = line.split()
            if len(parts) >= 2:
                core_data.append((parts[0], parts[1]))

        # Validate and format results
        if not core_data:
            logger.warning("No valid CPU data found after header")
            return ()

        # Extract unique Local CPU (default single value)
        local_cpu = core_data[0][0]

        # Create result tuple (Local CPU + all Remote CPUs)
        return (
            local_cpu,
            *(
                cpu[1]
                for cpu in core_data
                if cpu[1] not in self._ignored_cores
            ),
        )

    def init(self) -> None:
        """Finish product initialization."""
        cores = self.get_core_info() if self._conf.os == "nuttx" else ()
        self._core0 = cores[0] if cores else "core0"
        self._cur_core = self._core0
        self._cores = cores if cores else ("core0",)
        logger.info(f"Current product support cores: {self._cores}")

    @property
    def cur_core(self) -> Optional[str]:
        """Get current core."""
        return self._cur_core

    @property
    def cores(self) -> Tuple[str, ...]:
        """Get cores."""
        return self._cores

    def switch_core(self, target_core: str = "") -> int:
        """Switch the target core of the device.

        :param target_core: Core to switch to.

        :return: 0 on success, -1 on failure
        """
        if not self._core0 and not self._cur_core and not self._cores:
            raise ValueError("Product not initialized!")

        if not target_core:
            logger.debug(
                "The target_core has no value and cannot be switched."
            )
            return CmdStatus.NOTFOUND

        if self._core0 and target_core.lower() == self._core0.lower():
            logger.warning(
                "The target core is the main core, and the core"
                " is not switched."
            )
            return CmdStatus.SUCCESS

        logger.info(f"Attempting to switch to core: {target_core}")

        if target_core.lower() not in tuple(
            core.lower() for core in self._cores
        ):
            logger.debug(f"There is no {target_core} core in the device")
            return CmdStatus.NOTFOUND

        cmd = f"cu -l /dev/tty{target_core.upper()}\n\n"
        pattern = f"{target_core}>"
        rc = self.sendCommand(cmd, pattern, match_all=False, timeout=5)
        if rc == CmdStatus.SUCCESS:
            logger.info(f"Core switch to {target_core} succeeded")

        return rc

    def get_current_prompt(self) -> str:
        """Dynamically obtain the device current prompt.

        :return: The current prompt (e.g., ap>) (str)
                 or None: If the current prompt cannot be determined
        """
        core_pattern = rb"(\S+)>"
        matches: List[str] = []

        for _ in range(5):
            cmdret = self._device.send_cmd_read_until_pattern(
                b"\n", core_pattern, 1
            )

            if cmdret.valid_match() and cmdret.rematch:
                # Extract the matched core name
                core_name = (
                    cmdret.rematch.group(1).decode("utf-8", errors="ignore")
                    + ">"
                )
                matches.append(core_name)

        # Check whether two or more of the three results are consistent
        if len(matches) >= 2 and len(set(matches)) == 1:
            logger.info(f"The current prompt is {matches[0]}")
            return matches[0]

        logger.error("Failed to get current prompt, use default prompt.")
        return ">"

    def reboot(self, timeout: int = 30) -> bool:
        """Reboot the device by calling the device's reboot function.

        :param timeout: (int) Timeout in seconds for the reboot operation.
         Default is 30 seconds.

        :return: (bool) True if the reboot was successful, False otherwise.
        """
        logger.info(
            f"Attempting to reboot the device with " f"timeout: {timeout}s"
        )

        success = self._device.reboot(timeout=timeout)

        if success:
            logger.info("Device rebooted successfully.")
        else:
            logger.error("Failed to reboot the device.")

        return success

    def force_panic(self, timeout: int = 30) -> bool:
        """Trigger a kernel panic for debugging and core dump generation.

        :return: True if the force panic was successful, False otherwise.
        """
        panic_char = self.device.panic_char
        if not panic_char:
            logger.error("Force panic not supported.")
            return False
        self._device.log_event("force_panic")
        ret = self.device.send_ctrl_cmd(panic_char)
        if isinstance(ret, CmdStatus):
            return ret == CmdStatus.SUCCESS
        return bool(ret)

    @property
    def busyloop(self) -> bool:
        """Check if the device is in busy loop."""
        return self._device.busyloop

    @property
    def flood(self) -> bool:
        """Check if flood condition was detected."""
        return self._device.flood

    @property
    def crash(self) -> bool:
        """Check if the device is crashed."""
        return self._device.crash

    @property
    def notalive(self) -> bool:
        """Check if the device is dead."""
        return self._device.notalive

    @property
    def status(self) -> CoreStatus:
        """Check core status with all failure mode detection.

        :return: :class:`CoreStatus` representing the current state.
        """
        if self.crash:
            return CoreStatus.CRASH

        if self.busyloop:
            return CoreStatus.BUSYLOOP

        if self.flood:
            return CoreStatus.FLOOD

        if self.notalive:
            return CoreStatus.NOTALIVE

        return CoreStatus.NORMAL

    @property
    def device(self) -> "DeviceCommon":
        """Get underlying device."""
        return self._device

    @property
    def name(self) -> Any:
        """Get product name."""
        return self._name

    @property
    def prompt(self) -> bytes:
        """Get core prompt."""
        return self._prompt

    @property
    def conf(self) -> "CoreConfig":
        """Get core configuration."""
        return self._conf

    def start_log_collect(self, logs: "LogHandler") -> None:
        """Start device log collector."""
        self._device.start_log_collect(logs)

    def stop_log_collect(self) -> None:
        """Stop device log collector."""
        self._device.stop_log_collect()

    def start(self) -> None:
        """Start device."""
        self._device.start()

    def check_cmd(self, cmd_pattern: str) -> bool:
        """Check if a command pattern is available in the ELF binary.

        This method validates whether a specific command or set of
        commands is present in the core's ELF binary by searching for
        corresponding symbols. It supports both single commands and
        alternative command patterns separated by '|'.

        :param cmd_pattern: Command pattern to check for. Can contain
                           alternatives separated by '|'
                           (e.g., 'test1|test2')
        :return: True if the command pattern is found, False otherwise

        Note:
            - Requires ELF parser to be available in device
            - Supports alternative patterns with '|'
            - Used to validate core capabilities before executing
        """
        # Check if device supports command checking
        if hasattr(self._device, "elf_parser") and self._device.elf_parser:
            logger.debug(f"Checking command pattern: {cmd_pattern}")

            # Split by '|' to support alternative patterns
            alternatives = (
                cmd_pattern.split("|") if "|" in cmd_pattern else [cmd_pattern]
            )

            for pattern in alternatives:
                # For cmocka tests, append _main to symbol name
                symbol_pattern_str: str = (
                    f"{pattern}_main" if "cmocka" in pattern else pattern
                )

                # Support regex wildcards
                if ".*" in symbol_pattern_str:
                    symbol_pattern = re.compile(symbol_pattern_str)
                else:
                    tmp = symbol_pattern_str
                    symbol_pattern = tmp  # type: ignore[assignment]

                if self._device.elf_parser.has_symbol(symbol_pattern):
                    return True

            return False

        # Fallback: try to execute the command and check if it exists
        logger.warning(
            "ELF parser not available, trying command check for: "
            f"{cmd_pattern}"
        )

        # Send 'help' command to check if command exists
        result = self.sendCommandReadUntilPattern("help", timeout=5)

        if result.status == CmdStatus.SUCCESS:
            # Check if any of the command alternatives are in the help output
            alternatives = (
                cmd_pattern.split("|") if "|" in cmd_pattern else [cmd_pattern]
            )
            for pattern in alternatives:
                if pattern.lower() in result.output.lower():
                    return True

        return False
