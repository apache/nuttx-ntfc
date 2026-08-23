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

"""Check that a NuttX USB CDC/ACM link survives Linux runtime suspend.

A USB device driver that reports ``CLASS_SUSPEND`` but never
``CLASS_RESUME`` leaves ``cdcacm_suspend()``'s ``uart_connected(false)``
latched, after which ``serial.c`` refuses every board-side ``open()`` and
``write()`` on the CDC port with ``-ENOTCONN``.  The device stays
enumerated throughout, so the failure looks like a random USB wedge rather
than a deterministic one.

Linux hosts reach that state on their own: with ``power/control=auto`` and
the usual ``autosuspend_delay_ms=2000``, closing the tty is enough.

Each cycle forces a real runtime suspend, resumes the device by opening the
port, and measures what comes back.  A link that only flushes its stale CDC
TX buffer is caught by the tail measurement: bytes are counted both over the
whole read window and over its last second.

The board must transmit unprompted for this to measure anything -- a console
banner, a telemetry stream, anything periodic.

Requires a Linux host and sudo for two sysfs power attributes.
"""

import errno
import glob
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import serial  # type: ignore

# Overridden by the unit tests; the kernel offers no other location.
SYSFS_TTY = "/sys/class/tty"
DEV_SERIAL_BY_ID = "/dev/serial/by-id"
PROCFS = "/proc"

###############################################################################
# Class: UsbSuspendError
###############################################################################


class UsbSuspendError(Exception):
    """Raised when the host cannot be brought into a measurable state."""


###############################################################################
# Class: UsbSuspendConfig
###############################################################################


@dataclass
class UsbSuspendConfig:
    """Parameters of one suspend/resume measurement run."""

    device: Optional[str] = None
    cycles: int = 5
    delay_ms: int = 1000
    read_secs: float = 2.0
    tail_secs: float = 1.0
    min_bytes: int = 2000
    baud: int = 115200
    console: Optional[str] = None
    console_baud: int = 115200
    cdc_path: str = "/dev/ttyACM0"


###############################################################################
# Class: StreamRead
###############################################################################


@dataclass
class StreamRead:
    """Bytes seen in a read window and in its trailing part."""

    total: int = 0
    tail: int = 0
    error: str = ""


###############################################################################
# Class: CycleResult
###############################################################################


@dataclass
class CycleResult:
    """Outcome of one suspend/resume cycle."""

    suspended: bool = False
    stream: StreamRead = field(default_factory=StreamRead)
    note: str = ""


###############################################################################
# Function: read_attr
###############################################################################


def read_attr(base: str, name: str) -> Optional[str]:
    """Read one sysfs attribute.

    :param base: directory holding the attribute
    :param name: attribute file name
    :return: stripped contents, or ``None`` when it is not readable
    """
    try:
        with open(os.path.join(base, name), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


###############################################################################
# Function: usb_device_dir
###############################################################################


def usb_device_dir(tty_path: str) -> str:
    """Map a tty device node to the sysfs directory of its USB device.

    :param tty_path: tty node, e.g. ``/dev/ttyACM0``
    :return: sysfs directory of the USB device owning that tty
    :raises UsbSuspendError: when the tty is not backed by a USB device
    """
    tty = os.path.basename(os.path.realpath(tty_path))
    link = os.path.join(SYSFS_TTY, tty, "device")

    if not os.path.exists(link):
        raise UsbSuspendError(f"{tty_path} is not a tty backed by sysfs")

    node = os.path.realpath(link)

    # Walk up from the USB interface to the USB device that owns it.
    while node != "/":
        if os.path.exists(os.path.join(node, "idVendor")):
            return node

        node = os.path.dirname(node)

    raise UsbSuspendError(
        f"{tty_path} is not on a USB device (no idVendor in any parent)"
    )


###############################################################################
# Function: find_cdc_ports
###############################################################################


def find_cdc_ports() -> List[Tuple[str, str]]:
    """Return ``(port, usb sysfs dir)`` for every CDC/ACM port present."""
    found = []

    for path in sorted(glob.glob(os.path.join(DEV_SERIAL_BY_ID, "*"))):
        if not os.path.basename(os.path.realpath(path)).startswith("ttyACM"):
            continue

        try:
            found.append((path, usb_device_dir(path)))
        except UsbSuspendError:
            continue

    return found


###############################################################################
# Function: autodetect
###############################################################################


def autodetect() -> str:
    """Pick the CDC/ACM port when exactly one is present.

    :return: path of the only CDC/ACM port
    :raises UsbSuspendError: when there is no port, or more than one
    """
    found = find_cdc_ports()

    if not found:
        raise UsbSuspendError("no CDC/ACM port found, pass --device")

    if len(found) > 1:
        listing = "\n".join(
            f"  {path}  ({read_attr(usbdir, 'product')})"
            for path, usbdir in found
        )
        raise UsbSuspendError(
            f"several CDC/ACM ports present, pass --device:\n{listing}"
        )

    return found[0][0]


###############################################################################
# Function: port_holders
###############################################################################


def port_holders(dev: str) -> List[Tuple[str, str]]:
    """Return ``(pid, command)`` of every process holding ``dev`` open."""
    real = os.path.realpath(dev)
    holders = []

    for entry in glob.glob(os.path.join(PROCFS, "[0-9]*", "fd", "*")):
        try:
            if os.readlink(entry) != real:
                continue

            pid = entry.split(os.sep)[-3]
            comm = os.path.join(PROCFS, pid, "comm")

            with open(comm, encoding="utf-8") as handle:
                holders.append((pid, handle.read().strip()))
        except OSError:
            continue  # process exited, or not ours to inspect

    return sorted(set(holders))


###############################################################################
# Function: require_free_port
###############################################################################


def require_free_port(dev: str, baud: int) -> None:
    """Reject a port that another process holds open.

    An open port pins runtime PM, so the host never suspends and the run
    silently measures nothing.

    :param dev: CDC/ACM port to check
    :param baud: baud rate used for the probe open
    :raises UsbSuspendError: when the port is busy or cannot be opened
    """
    try:
        serial.Serial(os.path.realpath(dev), baud, timeout=0.2).close()
        return
    except OSError as exc:
        if exc.errno != errno.EBUSY:
            raise UsbSuspendError(f"cannot open {dev}: {exc}") from exc

    who = ", ".join(f"{name} (pid {pid})" for pid, name in port_holders(dev))
    raise UsbSuspendError(
        f"{dev} is held open by {who or 'another process'}.\n"
        "Close it first: an open port keeps the device active, so it "
        "never suspends."
    )


###############################################################################
# Function: read_stream
###############################################################################


def read_stream(
    dev: str, baud: int, seconds: float, tail_seconds: float
) -> StreamRead:
    """Read the port for ``seconds`` and count what arrives.

    Opening the port is also what resumes a suspended device.

    :param dev: CDC/ACM port to read
    :param baud: baud rate
    :param seconds: length of the read window
    :param tail_seconds: trailing part of the window counted separately
    :return: byte counts, or an open error
    """
    try:
        port = serial.Serial(os.path.realpath(dev), baud, timeout=0.2)
    except OSError as exc:
        return StreamRead(error=str(exc))

    start = time.time()
    result = StreamRead()

    try:
        while True:
            now = time.time() - start

            if now >= seconds:
                break

            chunk = port.read(4096)
            result.total += len(chunk)

            if now >= seconds - tail_seconds:
                result.tail += len(chunk)
    finally:
        port.close()

    return result


###############################################################################
# Function: console_probe
###############################################################################


def console_probe(console: str, baud: int, cdc_path: str) -> str:
    """Ask the board itself whether its CDC port is writable.

    :param console: board console port, separate from the CDC port
    :param baud: baud rate of that console
    :param cdc_path: CDC path as the board sees it
    :return: one-line verdict for the cycle report
    """
    try:
        port = serial.Serial(console, baud, timeout=0.2)
    except OSError as exc:
        return f"console unavailable ({exc})"

    out = b""

    try:
        port.write(b"\n")
        port.flush()
        time.sleep(0.3)
        port.reset_input_buffer()
        port.write(b"echo probe > " + cdc_path.encode() + b"\n")
        port.flush()

        deadline = time.time() + 2.0

        while time.time() < deadline:
            chunk = port.read(4096)

            if chunk:
                out += chunk
                deadline = time.time() + 0.5
    finally:
        port.close()

    text = out.decode(errors="replace")

    if "not connected" in text or "ENOTCONN" in text:
        return "board-side open failed: -ENOTCONN"

    if "failed" in text:
        return f"board-side open failed: {text.strip().splitlines()[-1]}"

    return "board-side open ok"


###############################################################################
# Class: UsbPower
###############################################################################


class UsbPower:
    """Runtime PM knobs of one USB device, restored on exit."""

    ATTRS = ("control", "autosuspend_delay_ms")

    def __init__(self, usbdir: str) -> None:
        """Snapshot the runtime PM attributes of a USB device.

        :param usbdir: sysfs directory of the USB device
        """
        self.path = os.path.join(usbdir, "power")
        self.saved: Dict[str, Optional[str]] = {
            key: self.get_attr(key) for key in self.ATTRS
        }

    def get_attr(self, name: str) -> Optional[str]:
        """Read one power attribute."""
        return read_attr(self.path, name)

    def set_attr(self, name: str, value: object) -> None:
        """Write one power attribute through ``sudo tee``.

        :param name: attribute file name
        :param value: value to write
        :raises UsbSuspendError: when the write is refused
        """
        target = os.path.join(self.path, name)
        proc = subprocess.run(
            ["sudo", "tee", target],
            input=str(value).encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )

        if proc.returncode != 0:
            reason = proc.stderr.decode().strip()
            raise UsbSuspendError(f"cannot write {target}: {reason}")

    def restore(self) -> None:
        """Put the saved runtime PM attributes back."""
        for name, value in self.saved.items():
            if value is not None:
                self.set_attr(name, value)

    def arm(self, delay_ms: int) -> None:
        """Re-arm the autosuspend timer.

        Once resumed, a device will not idle out again on its own until
        runtime PM is toggled, so every cycle has to re-allow it.

        :param delay_ms: autosuspend delay to force
        """
        self.set_attr("autosuspend_delay_ms", delay_ms)
        self.set_attr("control", "on")
        self.set_attr("control", "auto")

    def wait_suspended(self, timeout: float) -> bool:
        """Wait for ``runtime_status`` to reach ``suspended``.

        :param timeout: seconds to wait
        :return: True when the device actually suspended
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self.get_attr("runtime_status") == "suspended":
                return True

            time.sleep(0.1)

        return False


###############################################################################
# Class: UsbSuspendCheck
###############################################################################


class UsbSuspendCheck:
    """Drive host runtime suspend cycles and judge the CDC/ACM link."""

    def __init__(self, cfg: UsbSuspendConfig) -> None:
        """Resolve the device and take its runtime PM state.

        :param cfg: parameters of the run
        :raises UsbSuspendError: when no usable port could be claimed
        """
        self.cfg = cfg
        self.device = cfg.device or autodetect()
        self.usbdir = usb_device_dir(self.device)
        require_free_port(self.device, cfg.baud)
        self.power = UsbPower(self.usbdir)

    def report_setup(self) -> None:
        """Print what is being measured and how it was found."""
        print(f"device      {self.device} -> {os.path.realpath(self.device)}")
        print(
            f"usb         {os.path.basename(self.usbdir)}  "
            f"{read_attr(self.usbdir, 'idVendor')}:"
            f"{read_attr(self.usbdir, 'idProduct')}  "
            f"{read_attr(self.usbdir, 'product')}"
        )
        print(
            f"power       control={self.power.saved['control']} "
            f"autosuspend_delay_ms="
            f"{self.power.saved['autosuspend_delay_ms']} (restored on exit)"
        )
        print()

    def report_cycle(self, index: int, result: CycleResult) -> None:
        """Print the outcome of one cycle.

        :param index: 1-based cycle number
        :param result: what that cycle measured
        """
        if result.stream.error:
            print(
                f"[{index}] suspended={str(result.suspended):<5}  "
                f"OPEN FAILED: {result.stream.error}"
            )
            return

        print(
            f"[{index}] suspended={str(result.suspended):<5}  "
            f"read={result.stream.total:<7} "
            f"tail={result.stream.tail:<7} {result.note}"
        )

    def cycle(self) -> CycleResult:
        """Force one suspend, resume by opening the port, and measure."""
        cfg = self.cfg
        self.power.arm(cfg.delay_ms)
        suspended = self.power.wait_suspended(cfg.delay_ms / 1000.0 + 6.0)

        stream = read_stream(
            self.device, cfg.baud, cfg.read_secs, cfg.tail_secs
        )
        note = ""

        if cfg.console and suspended:
            # -ENOTCONN *during* suspend is correct on any build; the
            # defect is that it outlives the resume.  Pin the device
            # active so the board is asked about the resumed state.
            self.power.set_attr("control", "on")
            note = console_probe(cfg.console, cfg.console_baud, cfg.cdc_path)

        return CycleResult(suspended, stream, note)

    def verdict(self, results: List[CycleResult]) -> int:
        """Judge the collected cycles.

        :param results: one entry per cycle
        :return: 0 pass, 1 fail, 2 inconclusive
        """
        tested = [res for res in results if res.suspended]
        good = [res for res in tested if res.stream.tail >= self.cfg.min_bytes]

        print()

        if not tested:
            print(
                "INCONCLUSIVE: the host never suspended the device, so the "
                "bug was never exercised."
            )
            print(
                f"Check {self.usbdir}/power/runtime_usage; something holds "
                "a runtime PM reference."
            )
            return 2

        print(f"cycles with a verified suspend: {len(tested)}/{len(results)}")
        print(
            "of those, still streaming after resume: "
            f"{len(good)}/{len(tested)}"
        )
        print()

        if len(good) == len(tested):
            print("PASS: the link recovered from every suspend.")
            return 0

        print("FAIL: the link died after suspend and did not come back.")
        print(
            "Expected when the resume event never reaches the class driver: "
            "the first cycle can still flush the stale CDC TX buffer, later "
            "cycles read nothing."
        )
        return 1

    def run(self) -> int:
        """Run every cycle and report a verdict.

        :return: 0 pass, 1 fail, 2 inconclusive
        """
        self.report_setup()
        results: List[CycleResult] = []

        try:
            for index in range(1, self.cfg.cycles + 1):
                result = self.cycle()
                self.report_cycle(index, result)
                results.append(result)
        finally:
            self.power.restore()
            print()
            print(
                "power       restored to "
                f"control={self.power.get_attr('control')} "
                "autosuspend_delay_ms="
                f"{self.power.get_attr('autosuspend_delay_ms')}"
            )

        return self.verdict(results)
