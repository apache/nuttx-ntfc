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

"""Module containing NTFC usb-suspend command."""

from typing import Optional

import click

from ntfc.cli.environment import Environment, pass_environment
from ntfc.lib.usb.suspend import UsbSuspendConfig

###############################################################################
# Command: cmd_usbsuspend
###############################################################################


@click.command(name="usb-suspend")
@click.option(
    "-d",
    "--device",
    default=None,
    help="CDC/ACM port of the board. Default: autodetect",
)
@click.option(
    "-n",
    "--cycles",
    type=int,
    default=5,
    help="Suspend/resume cycles to run. Default: 5",
)
@click.option(
    "--delay-ms",
    type=int,
    default=1000,
    help="Autosuspend delay to force. Default: 1000",
)
@click.option(
    "--baud",
    type=int,
    default=115200,
    help="Baud rate of the CDC/ACM port. Default: 115200",
)
@click.option(
    "--read-secs",
    type=float,
    default=2.0,
    help="Read window per cycle. Default: 2.0",
)
@click.option(
    "--tail-secs",
    type=float,
    default=1.0,
    help="Trailing part of the window that must carry data. Default: 1.0",
)
@click.option(
    "--min-bytes",
    type=int,
    default=2000,
    help="Bytes required in the tail window. Default: 2000",
)
@click.option(
    "--console",
    default=None,
    help="Board console, to probe the port from the board after resume",
)
@click.option(
    "--console-baud",
    type=int,
    default=115200,
    help="Baud rate of that console. Default: 115200",
)
@click.option(
    "--cdc-path",
    default="/dev/ttyACM0",
    help="CDC path as the board sees it. Default: /dev/ttyACM0",
)
@pass_environment
def cmd_usbsuspend(
    ctx: Environment,
    device: Optional[str],
    cycles: int,
    delay_ms: int,
    baud: int,
    read_secs: float,
    tail_secs: float,
    min_bytes: int,
    console: Optional[str],
    console_baud: int,
    cdc_path: str,
) -> bool:
    """Check that a USB CDC/ACM link survives host runtime suspend.

    Needs a Linux host, sudo for two sysfs power attributes, and a board
    that transmits unprompted on the CDC port.  Needs no NuttX
    configuration, so it takes no --confpath.
    """
    ctx.runusbsuspend = True
    ctx.usbsuspend = UsbSuspendConfig(
        device=device,
        cycles=cycles,
        delay_ms=delay_ms,
        baud=baud,
        read_secs=read_secs,
        tail_secs=tail_secs,
        min_bytes=min_bytes,
        console=console,
        console_baud=console_baud,
        cdc_path=cdc_path,
    )

    return True
