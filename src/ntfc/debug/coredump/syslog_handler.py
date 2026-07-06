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

"""Syslog coredump handler for NuttX BOARD_COREDUMP_SYSLOG output."""

import base64
import io
import struct
from typing import TYPE_CHECKING, Optional

import lzf  # type: ignore[import-untyped]

from ntfc.debug.coredump.base import CoredumpHandler
from ntfc.log.logger import logger

if TYPE_CHECKING:
    from pathlib import Path

    from ntfc.device.common import DeviceCommon

START_MARKER = "Start coredump"
FINISH_MARKER = "Finish coredump"


###############################################################################
# Class: SyslogHandler
###############################################################################


class SyslogHandler(CoredumpHandler):
    """Decode a coredump embedded in the device's syslog output.

    NuttX with ``CONFIG_BOARD_COREDUMP_SYSLOG`` emits the coredump as a
    base64 block between ``Start coredump`` and ``Finish coredump``
    lines.  The decoded payload is a stream of ``ZV`` lzf blocks.

    :param device: Device whose output contains the coredump.
    """

    def __init__(self, device: "DeviceCommon") -> None:
        """Initialize :class:`SyslogHandler`.

        :param device: Device instance providing ``output_tail()``.
        """
        super().__init__()
        self._device = device

    @property
    def name(self) -> str:
        """Return the handler name ``"syslog"``.

        :return: ``"syslog"``
        """
        return "syslog"

    @property
    def priority(self) -> int:
        """Return the handler priority ``25``.

        :return: ``25``
        """
        return 25

    def collect(self, output_dir: "Path", prefix: str) -> bool:
        """Extract, decode and write the coredump from device output.

        The output tail is cleared as soon as it is read, regardless of
        outcome, so a later, unrelated test can never pick up markers
        left over from this (or an even earlier) collection attempt.

        :param output_dir: Directory where the coredump file is written.
        :param prefix: Filename prefix for the output file.
        :return: ``True`` when a coredump was decoded and saved.
        """
        output = self._device.output_tail()
        self._device.reset_output_tail()

        payload = self._extract_payload(output)
        if payload is None:
            logger.warning("syslog: no coredump markers in device output")
            return False

        try:
            raw = base64.b64decode(payload)
        except ValueError as exc:
            logger.warning(f"syslog: base64 decode failed: {exc}")
            return False

        data = self._decompress(raw)
        if not data:
            logger.warning("syslog: empty coredump payload")
            return False

        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / f"{prefix}.core"
        dest.write_bytes(data)
        logger.debug(f"syslog: saved coredump {dest} ({len(data)} bytes)")
        return True

    @staticmethod
    def _extract_payload(output: str) -> Optional[str]:
        """Return the base64 payload between the last complete pair.

        Marker pairs are committed atomically: a ``Start coredump``
        line only takes effect once it is matched by a following
        ``Finish coredump`` line, and the last such complete pair
        wins. A trailing, unterminated ``Start coredump`` line (with
        no matching ``Finish coredump`` after it) is ignored and does
        not discard a previously recorded valid pair.

        Each payload line carries a syslog prefix; only the text after
        the last space is coredump data.

        :param output: Recent raw device output.
        :return: Concatenated base64 text, or ``None``.
        """
        lines = output.splitlines()
        pending: Optional[int] = None
        start = finish = None
        for i, line in enumerate(lines):
            if START_MARKER in line:
                pending = i
            elif FINISH_MARKER in line and pending is not None:
                start, finish = pending, i
                pending = None
        if start is None or finish is None:
            return None

        chars = []
        for line in lines[start + 1 : finish]:
            index = line.rfind(" ")
            if index > 0:
                line = line[index + 1 :]
            chars.append(line.strip())
        return "".join(chars)

    @staticmethod
    def _decompress(data: bytes) -> bytes:
        """Decode a stream of ``ZV`` lzf blocks.

        :param data: Base64-decoded payload.
        :return: Decompressed coredump bytes (empty on failure).
        """
        stream = io.BytesIO(data)
        output = bytearray()
        while True:
            if stream.read(2) != b"ZV":
                break
            typ = stream.read(1)
            clen_raw = stream.read(2)
            if len(clen_raw) < 2:
                break
            clen = struct.unpack(">H", clen_raw)[0]
            if typ == b"\x00":
                output.extend(stream.read(clen))
            elif typ == b"\x01":
                ulen_raw = stream.read(2)
                if len(ulen_raw) < 2:
                    break
                ulen = struct.unpack(">H", ulen_raw)[0]
                block = SyslogHandler._lzf_decompress_block(
                    stream.read(clen), ulen
                )
                if block is None:
                    break
                output.extend(block)
            else:
                break
        return bytes(output)

    @staticmethod
    def _lzf_decompress_block(compressed: bytes, ulen: int) -> Optional[bytes]:
        """Decompress a single liblzf-framed block.

        The ``lzf`` package (a CFFI binding) exposes no module-level
        ``decompress(data, length)`` helper; the C function is called
        directly via ``lzf.lib.lzf_decompress``, which writes into a
        pre-allocated output buffer and returns the number of bytes
        written (``0`` on error), mirroring the package's own
        ``_iter_decompress`` implementation.

        :param compressed: Compressed block bytes.
        :param ulen: Expected decompressed length.
        :return: Decompressed bytes, or ``None`` on failure.
        """
        out_buf = lzf.ffi.new("char[]", max(ulen, 1))
        written = lzf.lib.lzf_decompress(
            compressed, len(compressed), out_buf, ulen
        )
        if written == 0 or written != ulen:
            logger.warning("syslog: lzf block decompression failed")
            return None
        return bytes(lzf.ffi.unpack(out_buf, written))
