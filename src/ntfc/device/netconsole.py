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

"""Host side of the NuttX netdev console (CONFIG_CONSOLE_NETDEV).

The NuttX console is carried over a network transport instead of the
emulator's serial port. UDP and CAN ISO-TP are supported; both are
datagram transports, so writes are split into datagrams that fit the
console receive buffer of the target.
"""

import select
import socket
import struct
from typing import Any, Dict, Optional, Tuple

from ntfc.log.logger import logger

###############################################################################
# Class: NetConsole
###############################################################################


class NetConsole:
    """Common interface of a host netdev console transport."""

    # bytes per datagram, below the default CONSOLE_NETDEV_RXBUFSIZE (256)
    DEFAULT_CHUNK = 128
    RECV_SIZE = 4096
    # wait for the previous datagram to leave (ISO-TP sends one at a time)
    SEND_TIMEOUT = 2.0

    def __init__(self, cfg: Dict[str, Any]):
        """Initialize the transport.

        :param cfg: ``netconsole`` section of the core configuration
        """
        self._cfg = cfg
        self._sock: Optional[socket.socket] = None
        self._chunk = int(cfg.get("chunk", self.DEFAULT_CHUNK))
        if self._chunk <= 0:
            raise ValueError("netconsole chunk must be positive")

    @property
    def is_open(self) -> bool:
        """Return True if the transport socket is open."""
        return self._sock is not None

    def _socket(self) -> socket.socket:  # pragma: no cover
        """Create and bind the transport socket."""
        raise NotImplementedError

    def _send(self, data: bytes) -> None:  # pragma: no cover
        """Send one datagram to the target."""
        raise NotImplementedError

    def _recv(self) -> bytes:
        """Receive one datagram from the target."""
        assert self._sock
        return self._sock.recv(self.RECV_SIZE)

    def start(self) -> None:
        """Start the transport. Must be done before the target boots."""
        if self._sock:
            return
        sock = self._socket()
        sock.setblocking(False)
        self._sock = sock

    def stop(self) -> None:
        """Stop the transport."""
        if self._sock:
            self._sock.close()
        self._sock = None

    def read(self) -> bytes:
        """Read the console data that is available now."""
        if not self._sock:
            return b""

        data = b""
        while True:
            ready, _, _ = select.select([self._sock], [], [], 0)
            if not ready:
                break
            try:
                data += self._recv()
            except (BlockingIOError, InterruptedError):
                break
            except OSError as e:
                logger.warning(f"netconsole: receive failed: {e}")
                break
        return data

    def write(self, data: bytes) -> None:
        """Write console data, one datagram per chunk."""
        if not self._sock:
            return

        for i in range(0, len(data), self._chunk):
            _, ready, _ = select.select(
                [], [self._sock], [], self.SEND_TIMEOUT
            )
            if not ready:
                logger.warning("netconsole: send timeout, dropped")
                return
            self._send(data[i : i + self._chunk])


###############################################################################
# Class: NetConsoleUdp
###############################################################################


class NetConsoleUdp(NetConsole):
    """UDP netdev console.

    NTFC listens on ``port`` (CONFIG_CONSOLE_NETDEV_PORT) for the datagrams
    the target sends to CONFIG_CONSOLE_NETDEV_IPADDR and replies to the
    address the last datagram came from.
    """

    DEFAULT_PORT = 55000

    def __init__(self, cfg: Dict[str, Any]):
        """Initialize the UDP transport.

        :param cfg: ``netconsole`` section of the core configuration
        """
        NetConsole.__init__(self, cfg)
        self._bind = str(cfg.get("bind", "0.0.0.0"))
        self._port = int(cfg.get("port", self.DEFAULT_PORT))
        self._peer: Optional[Tuple[str, int]] = None

    def _socket(self) -> socket.socket:
        """Create the UDP socket bound to the console port."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._bind, self._port))
        logger.info(f"netconsole: UDP on {self._bind}:{self._port}")
        return sock

    def _recv(self) -> bytes:
        """Receive one datagram and remember where it came from."""
        assert self._sock
        data, addr = self._sock.recvfrom(self.RECV_SIZE)
        if self._peer != (addr[0], addr[1]):
            logger.info(f"netconsole: target is {addr[0]}:{addr[1]}")
            self._peer = (addr[0], addr[1])
        return data

    def _send(self, data: bytes) -> None:
        """Send one datagram to the target."""
        assert self._sock
        if self._peer is None:
            logger.warning("netconsole: target address unknown, dropped")
            return
        self._sock.sendto(data, self._peer)


###############################################################################
# Class: NetConsoleIsotp
###############################################################################


class NetConsoleIsotp(NetConsole):
    """CAN ISO-TP netdev console (Linux ``can_isotp``).

    ``rx_id`` is the CAN ID the target sends on (CONFIG_CONSOLE_NETDEV_PORT)
    and ``tx_id`` the CAN ID it receives on (CONFIG_CONSOLE_NETDEV_PORT + 1).
    With ``fd: true`` the host uses CAN FD frames like a target built with
    CONFIG_NET_CAN_CANFD.
    """

    DEFAULT_RX_ID = 2000
    SOL_CAN_ISOTP = 106  # SOL_CAN_BASE (100) + CAN_ISOTP (6)
    CAN_ISOTP_LL_OPTS = 5
    CANFD_MTU = 72
    CANFD_MAX_DLEN = 64

    def __init__(self, cfg: Dict[str, Any]):
        """Initialize the ISO-TP transport.

        :param cfg: ``netconsole`` section of the core configuration
        """
        NetConsole.__init__(self, cfg)
        self._ifname = str(cfg.get("interface", "can0"))
        self._rx_id = int(cfg.get("rx_id", self.DEFAULT_RX_ID))
        self._tx_id = int(cfg.get("tx_id", self._rx_id + 1))
        self._fd = bool(cfg.get("fd", False))

    def _socket(self) -> socket.socket:
        """Create the ISO-TP socket bound to the console CAN IDs."""
        proto = getattr(socket, "CAN_ISOTP", 6)
        sock = socket.socket(socket.AF_CAN, socket.SOCK_DGRAM, proto)
        try:
            if self._fd:
                opts = struct.pack(
                    "=BBB", self.CANFD_MTU, self.CANFD_MAX_DLEN, 0
                )
                sock.setsockopt(
                    self.SOL_CAN_ISOTP, self.CAN_ISOTP_LL_OPTS, opts
                )
            sock.bind((self._ifname, self._rx_id, self._tx_id))
        except OSError:
            sock.close()
            raise
        logger.info(
            f"netconsole: ISO-TP on {self._ifname} "
            f"rx=0x{self._rx_id:x} tx=0x{self._tx_id:x}"
        )
        return sock

    def _send(self, data: bytes) -> None:
        """Send one ISO-TP message to the target."""
        assert self._sock
        self._sock.send(data)


###############################################################################
# Function: get_netconsole
###############################################################################

_NETCONSOLES = {
    "udp": NetConsoleUdp,
    "isotp": NetConsoleIsotp,
}


def get_netconsole(cfg: Optional[Dict[str, Any]]) -> Optional[NetConsole]:
    """Return the netdev console transport for a ``netconsole`` section.

    :param cfg: ``netconsole`` section of the core configuration or None
    :return: transport instance or None if the section is not given
    """
    if not isinstance(cfg, dict) or not cfg:
        return None

    kind = cfg.get("type")
    factory = _NETCONSOLES.get(str(kind))
    if factory is None:
        raise ValueError(f"unsupported netconsole type: {kind}")
    return factory(cfg)
