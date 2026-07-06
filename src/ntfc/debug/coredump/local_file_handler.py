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

"""Local-file coredump handler for host-filesystem corefiles."""

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set

from ntfc.debug.coredump.base import CoredumpHandler
from ntfc.log.logger import logger

if TYPE_CHECKING:
    from ntfc.debug.config import LocalFileConfig

###############################################################################
# Class: LocalFileHandler
###############################################################################


class LocalFileHandler(CoredumpHandler):
    """Collect corefiles written directly to the host filesystem.

    Useful for QEMU or simulator targets configured to write their
    coredump into a host directory.

    :param cfg: Local-file section of the product debug configuration.
    """

    def __init__(self, cfg: "LocalFileConfig") -> None:
        """Initialize :class:`LocalFileHandler`.

        :param cfg: Local-file configuration object.
        """
        super().__init__()
        self._cfg = cfg
        self._consumed: Set[Path] = set()

    @property
    def name(self) -> str:
        """Return the handler name ``"local_file"``."""
        return "local_file"

    @property
    def priority(self) -> int:
        """Return the handler priority ``15``."""
        return 15

    def is_available(self) -> bool:
        """Return ``True`` when the watched directory exists."""
        return Path(self._cfg.core_dir).is_dir()

    def collect(self, output_dir: "Path", prefix: str) -> bool:
        """Move the newest unconsumed corefile into the result dir.

        :param output_dir: Directory where the coredump file is written.
        :param prefix: Filename prefix for the output file.
        :return: ``True`` when a corefile was collected.
        """
        candidate = self._newest_corefile()
        if candidate is None:
            logger.debug("local_file: no new corefile found")
            return False

        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / f"{prefix}.core"
        shutil.move(str(candidate), dest)
        self._consumed.add(candidate)
        logger.debug(f"local_file: collected {candidate} -> {dest}")
        return True

    def _newest_corefile(self) -> Optional[Path]:
        """Return the newest matching, non-empty, unconsumed corefile.

        :return: Corefile path or ``None``.
        """
        directory = Path(self._cfg.core_dir)
        candidates = [
            p
            for p in directory.glob(self._cfg.pattern)
            if p.is_file() and p not in self._consumed and p.stat().st_size > 0
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)
