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

"""Device common interface."""

import re
import shlex
import subprocess
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from ntfc.device.cmds import CmdReturn, CmdStatus
from ntfc.device.state import DeviceState, DeviceStateManager
from ntfc.log.logger import logger

from .getos import get_os

if TYPE_CHECKING:
    from ntfc.coreconfig import CoreConfig
    from ntfc.log.handler import LogHandler

_ANSI_ESCAPE_RE = re.compile(rb"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

__all__ = ["CmdReturn", "CmdStatus", "DeviceCommon"]


###############################################################################
# Class: DeviceCommon
###############################################################################


class DeviceCommon(ABC):
    """Device common interface."""

    _BUSY_LOOP_TIMEOUT = 180  # 180 sec with no data read from target
    _OUTPUT_TAIL_MAX = 4 * 1024 * 1024

    def __init__(self, conf: "CoreConfig", echo: bool = True):
        """Initialize common device."""
        self._conf = conf
        # get OS abstraction
        self._dev = get_os(conf)

        # logs handler
        self._logs: Optional[LogHandler] = None
        self._pending_device_events: list[str] = []

        # device health - use state manager with heartbeat support

        self._state_mgr = DeviceStateManager(
            busyloop_threshold=float(self._BUSY_LOOP_TIMEOUT),
            crash_signatures=self._dev.crash_signatures,
            heartbeat_send_fn=self.send_cmd_read_until_pattern,
        )
        self.clear_fault_flags()

        self._read_all_sleep = 0.1
        self._has_echo = echo
        self._start_time: Optional[float] = None
        self._output_tail_buf = bytearray()

    def _mark_started(self) -> None:
        """Mark device start time for runtime tracking."""
        self._start_time = time.monotonic()

    def _runtime_since_start(self) -> Optional[float]:
        """Return runtime since start, if available."""
        if self._start_time is None:
            return None
        return time.monotonic() - self._start_time

    @property
    def pid(self) -> Optional[int]:
        """Return the device process PID, or ``None`` when not host-based."""
        return None

    def _output_tail_append(self, data: bytes) -> None:
        """Append raw output to the capped tail buffer.

        :param data: Raw bytes read from the device.
        """
        self._output_tail_buf.extend(data)
        if len(self._output_tail_buf) > self._OUTPUT_TAIL_MAX:
            del self._output_tail_buf[: -self._OUTPUT_TAIL_MAX]

    def output_tail(self) -> str:
        """Return the most recent raw device output.

        :return: Up to ``_OUTPUT_TAIL_MAX`` bytes of output, decoded.
        """
        return self._output_tail_buf.decode(errors="replace")

    def reset_output_tail(self) -> None:
        """Discard the buffered output tail.

        Called by consumers (e.g.
        :class:`~ntfc.debug.coredump.syslog_handler.SyslogHandler`)
        once they have read :meth:`output_tail`, so markers from an
        earlier, unrelated crash cannot be picked up again by a later
        test that merely reuses the same handler.
        """
        self._output_tail_buf.clear()

    def _log_device_line(self, line: str) -> None:
        """Log or buffer a pre-formatted device log line."""
        if self._logs is None:
            self._pending_device_events.append(line)
            return
        self._logs.write_device(line)

    def _log_device_event(self, message: str) -> None:
        """Log device control/status event with timestamp."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self._log_device_line(f"{ts} | {message}\n")

    def _log_runtime_event(self, action: str) -> None:
        """Log runtime duration for a device action."""
        runtime = self._runtime_since_start()
        if runtime is None:
            message = f"{action} runtime=unknown"
        else:
            message = f"{action} runtime={runtime:.2f}s"
        logger.info(message)
        self._log_device_event(message)

    def _log_console_input(self, data: bytes) -> None:
        """Log console input (commands) with timestamp."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        text = data.decode("utf-8", errors="replace")
        text = text.replace("\r", "\\r").replace("\n", "\\n")
        self._log_device_line(f"{ts} | console_in | {text}\n")

    def _console_log(self, data: bytes) -> None:
        """Log console output."""
        if self._logs is not None:  # pragma: no cover
            self._logs.write_console(data)

    def _wait_for_boot(self, timeout: int = 5) -> bool:
        """Wait for device booted."""
        self._log_device_event(f"wait_for_boot start timeout={timeout}s")
        start = time.monotonic()
        end_time = time.time() + timeout
        while time.time() < end_time:
            # send new line and expect prompt in returned data
            ret = self.send_command(b"\n", 1)
            if self._dev.prompt in ret:
                elapsed = time.monotonic() - start
                self._log_device_event(
                    f"wait_for_boot exit status=success elapsed={elapsed:.2f}s"
                )
                return True

            time.sleep(1)

        elapsed = time.monotonic() - start
        self._log_device_event(
            f"wait_for_boot exit status=timeout elapsed={elapsed:.2f}s"
        )
        return False

    def _read_all(self, timeout: float = 1.0) -> bytes:
        """Read data from the device."""
        output = b""
        end_time = time.time() + timeout

        while True:
            chunk = self._read()
            output += chunk
            self._output_tail_append(chunk)
            time_now = time.time()

            # check for any sign of system crash
            if self._state_mgr.check_crash(output):  # pragma: no cover
                logger.info("Crash detected!")
                self._log_device_event("fault detected: crash")
                break

            # check for busy loop
            # trigger an error if there was no data to read for a long time
            if not chunk:
                if (  # pragma: no cover
                    not self._state_mgr.is_busy_loop()
                    and self._state_mgr.check_busy_loop_timeout()
                ):
                    self._log_device_event("fault detected: busyloop")
                    break
            else:
                self._state_mgr.update_activity()

            # check for timeout
            if time_now > end_time:
                break

            # need to sleep for a while, otherwise host CPU load jumps to 100%
            time.sleep(self._read_all_sleep)

        clean = _ANSI_ESCAPE_RE.sub(b"", output)

        return clean

    def dev_is_health(self) -> bool:  # pragma: no cover
        """Check if the serial device is OK."""
        if not self._dev_is_health_priv():
            return False
        return not self._state_mgr.is_unhealthy()

    @DeviceStateManager.mark_command
    def send_command(self, cmd: bytes | str, timeout: int = 1) -> bytes:
        """Send command to the device and get the response."""
        # convert string to bytes
        if not isinstance(cmd, bytes):
            cmd = cmd.encode("utf-8")

        self._log_console_input(cmd)

        # read any pending output and drop
        _ = self._read_all(timeout=0)
        self._console_log(_)

        # log written command if echo is not supported by DTU
        if not self._has_echo:
            self._console_log(cmd)

        # write command and get response
        self._write(cmd)
        rsp = self._read_all(timeout=timeout)

        logger.info("Sent command: %s", cmd)

        # console log
        self._console_log(rsp)
        return rsp

    def _read_until_pattern_loop(  # noqa: C901
        self,
        initial_output: bytes,
        pattern: bytes,
        timeout: int,
        fail_pattern: Optional[bytes] = None,
    ) -> CmdReturn:
        """Read device output until pattern or fail_pattern matches.

        :param initial_output: Output already accumulated before the loop
         (e.g. command echo)
        :param pattern: Regex pattern whose match signals success
        :param timeout: Timeout in seconds
        :param fail_pattern: Regex pattern whose match signals failure and
         causes an immediate exit

        :return: CmdReturn : command return data
        """
        end_time = time.time() + timeout
        output = initial_output
        _match = None
        ret = CmdStatus.TIMEOUT

        while True:
            chunk = self._read_all(0.1)
            output += chunk
            self._console_log(chunk)

            # limit output data to process, otherwise re.search can stack
            # REVISIT: its possible to miss some pattern in output
            output_max = 100000
            if len(output) > output_max:  # pragma: no cover
                output = output[-output_max:]

            if fail_pattern and re.search(fail_pattern, output):
                logger.debug(
                    f">>fail match: {output!r}, search: {fail_pattern!r}<<"
                )
                ret = CmdStatus.FAILED
                break

            _match = re.search(pattern, output)
            if _match:
                logger.debug(f">>match: {output!r}, search: {pattern!r}<<")
                ret = CmdStatus.SUCCESS
                break

            # check for timeout
            if time.time() > end_time:
                ret = CmdStatus.TIMEOUT
                break

            # exit before timeout if dev crashed
            if not self.dev_is_health():  # pragma: no cover
                break

        # check for output flood condition.
        # If we still get some data from dev, its possible that we stuck
        # in some command
        if ret == CmdStatus.TIMEOUT:
            chunk = self._read_all(0.1)
            if len(chunk) > 0:
                if not self._state_mgr.is_unhealthy():
                    self._log_device_event("fault detected: flood")
                self._state_mgr.set_unhealthy("Flood detected")
            self._console_log(chunk)

        return CmdReturn(ret, _match, output.decode("utf-8", errors="replace"))

    @DeviceStateManager.mark_command
    def send_cmd_read_until_pattern(
        self,
        cmd: bytes,
        pattern: bytes,
        timeout: int,
        fail_pattern: Optional[bytes] = None,
    ) -> CmdReturn:
        """Send command to device and read until the specified pattern.

        :param cmd: (bytes) command to send to device
        :param pattern: (bytes, or list of (bytes), optional)
         String or regex pattern to look for. If a list,
         patterns will be concatenated with '.*'.
         The pattern will be converted to bytes for matching.
         Default is None.
        :param timeout: (int) timeout value in seconds
        :param fail_pattern: (bytes, optional) Regex pattern whose presence in
         the output immediately terminates the read and returns FAILED.

        :return: CmdReturn : command return data
        """
        if not isinstance(cmd, bytes):
            raise TypeError("Command must be bytes")

        if not isinstance(pattern, bytes):
            raise TypeError("Pattern must be bytes")

        self._log_console_input(cmd)

        # Clear buffer for any spurious data
        _ = self._read_all(timeout=0)
        self._console_log(_)

        # Log written command if echo is not supported by DTU
        if not self._has_echo:  # pragma: no cover
            self._console_log(cmd)

        # Write command
        self._write(cmd)
        logger.info("Sent command: %s", cmd)

        # Read initial response
        initial_output = self._read_all(timeout=0)
        self._console_log(initial_output)

        return self._read_until_pattern_loop(
            initial_output, pattern, timeout, fail_pattern
        )

    @DeviceStateManager.mark_command
    def read_until_pattern(
        self,
        pattern: bytes,
        timeout: int,
        fail_pattern: Optional[bytes] = None,
    ) -> CmdReturn:
        """Read device output until a pattern without sending a command.

        Useful for catching output from an already-running program.

        :param pattern: Regex pattern whose match signals success
        :param timeout: Timeout in seconds
        :param fail_pattern: (bytes, optional) Regex pattern whose presence in
         the output immediately terminates the read and returns FAILED.

        :return: CmdReturn : command return data
        """
        if not isinstance(pattern, bytes):
            raise TypeError("Pattern must by bytes")

        return self._read_until_pattern_loop(
            b"", pattern, timeout, fail_pattern
        )

    def send_ctrl_cmd(self, ctrl_char: str) -> CmdStatus:
        """Send control command to the device."""
        self._log_device_event(f"send_ctrl_cmd ctrl+{ctrl_char}")
        self._write_ctrl(ctrl_char)
        logger.info(f"Sent Ctrl+{ctrl_char}.")
        return CmdStatus.SUCCESS

    def log_event(self, message: str) -> None:
        """Public hook for device event logging."""
        self._log_device_event(message)

    def start_log_collect(self, logs: "LogHandler") -> None:
        """Start device log collector."""
        self._logs = logs
        if self._pending_device_events:
            self._logs.writelines_device(self._pending_device_events)
            self._pending_device_events.clear()

    def stop_log_collect(self) -> None:
        """Stop device log collector."""
        self._logs = None

    def clear_fault_flags(self) -> None:
        """Clear fault flags."""
        self._state_mgr.reset_all_states()

    def _system_cmd(self, cmd: str) -> None:  # pragma: no cover
        logger.info(f"system command: {cmd}")
        subprocess.run(
            shlex.split(cmd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

    @property
    def prompt(self) -> bytes:
        """Return target device prompt."""
        return self._dev.prompt

    @property
    def no_cmd(self) -> str:
        """Return command not found string."""
        return self._dev.no_cmd

    @property
    def busyloop(self) -> bool:
        """Check if the device is in busy loop."""
        return self._state_mgr.is_busy_loop()

    @property
    def flood(self) -> bool:
        """Check if the device is in flood state."""
        return self._state_mgr.get_current_state() == DeviceState.UNHEALTHY

    @property
    def crash(self) -> bool:
        """Check if the device is crashed."""
        return self._state_mgr.is_crashed()

    @property
    def panic_char(self) -> str:
        """Get force panic character."""
        return self._dev.panic_char

    @abstractmethod
    def _read(self) -> bytes:
        """Read data from the device."""

    @abstractmethod
    def _write(self, data: bytes) -> None:
        """Write to the device."""

    @abstractmethod
    def _write_ctrl(self, c: str) -> None:
        """Write a control character to the device."""

    @abstractmethod
    def _dev_is_health_priv(self) -> bool:
        """Check if the device is OK."""

    def start(self) -> None:
        """Start device."""
        self._mark_started()
        self._log_device_event("start")
        self._start_impl()

    def stop(self) -> None:
        """Stop the device and release resources."""
        self._log_device_event("stop")
        self._stop_impl()

    @property
    @abstractmethod
    def name(self) -> str:
        """Get device name."""

    @property
    @abstractmethod
    def notalive(self) -> bool:
        """Check if the device is dead."""

    def poweroff(self, hard: bool = True) -> bool:
        """Poweroff the device.

        :param hard: (bool) If True use hardware poweroff (system command for
         serial devices, process restart for host devices). If False use
         software poweroff (OS shell command). Default is True.
        :return: (bool) True if the poweroff was successful, False otherwise.
        """
        self._log_runtime_event("poweroff")
        if not hard:
            self.send_command(self._dev.poweroff_cmd)
            return True
        return self._poweroff_impl()

    def reboot(self, timeout: int = 1, hard: bool = True) -> bool:
        """Reboot the device.

        :param timeout: (int) Timeout in seconds for the reboot operation.
        :param hard: (bool) If True use hardware reboot (system command for
         serial devices, process restart for host devices). If False use
         software reboot (OS shell command). Default is True.
        :return: (bool) True if the reboot was successful, False otherwise.
        """
        self._log_runtime_event("reboot")
        self._log_device_event(f"reboot timeout={timeout}s")
        if not hard:
            self.send_command(self._dev.reboot_cmd)
            self._mark_started()
            return self._wait_for_boot(timeout)
        success = self._reboot_impl(timeout)
        if success:
            self._mark_started()
            success = self._wait_for_boot(timeout)
        return success

    @abstractmethod
    def _start_impl(self) -> None:
        """Start device implementation."""

    @abstractmethod
    def _stop_impl(self) -> None:
        """Stop the device and release resources."""

    @abstractmethod
    def _poweroff_impl(self) -> bool:
        """Hardware poweroff device implementation.

        :return: (bool) True on success, False otherwise.
        """

    @abstractmethod
    def _reboot_impl(self, timeout: int) -> bool:
        """Hardware reboot device implementation.

        :param timeout: (int) Timeout in seconds.
        :return: (bool) True on success, False otherwise.
        """
