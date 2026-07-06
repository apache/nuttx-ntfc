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

"""Coredump manager: selects and invokes the best available handler."""

from typing import TYPE_CHECKING, List

from ntfc.log.logger import logger

if TYPE_CHECKING:
    from pathlib import Path

    from ntfc.debug.config import CoredumpConfig
    from ntfc.debug.coredump.base import CoredumpHandler

###############################################################################
# Class: CoredumpManager
###############################################################################


class CoredumpManager:
    """Orchestrates coredump collection across registered handlers.

    Handlers are selected by priority (lowest value wins).  When
    :attr:`~CoredumpConfig.collection_type` is not ``"auto"`` only the
    handler whose :attr:`~CoredumpHandler.name` matches that value is
    considered.

    :param cfg: Coredump section of the product debug configuration.
    """

    def __init__(self, cfg: "CoredumpConfig") -> None:
        """Initialize :class:`CoredumpManager`.

        :param cfg: Coredump configuration object.
        """
        self._cfg = cfg
        self._handlers: "List[CoredumpHandler]" = []
        self._count: int = 0

    def register(self, handler: "CoredumpHandler") -> None:
        """Register a handler with this manager.

        :param handler: :class:`~ntfc.debug.coredump.base.CoredumpHandler`
            instance to add.
        """
        self._handlers.append(handler)

    def collect(self, output_dir: "Path", prefix: str) -> bool:
        """Collect a coredump using the best available handler.

        Handlers are tried in priority order until one succeeds, so a
        transient failure of the preferred backend falls back to the
        next configured one.

        Returns ``False`` when:

        * coredump collection is disabled in configuration,
        * the per-session limit has been reached, or
        * no enabled and available handler succeeds.

        The collection count is incremented only on a successful collection.

        :param output_dir: Directory where the coredump file is written.
        :param prefix: Filename prefix passed through to the handler.
        :return: ``True`` on success, ``False`` otherwise.
        """
        if not self._cfg.enable:
            logger.debug("coredump collection disabled")
            return False

        if self._count >= self._cfg.limit:
            logger.debug(
                f"coredump limit reached ({self._count}/{self._cfg.limit})"
            )
            return False

        candidates = [
            h for h in self._handlers if h.is_enabled() and h.is_available()
        ]

        if self._cfg.collection_type != "auto":
            candidates = [
                h for h in candidates if h.name == self._cfg.collection_type
            ]

        candidates.sort(key=lambda h: h.priority)

        if not candidates:
            logger.debug("no available coredump handler")
            return False

        for handler in candidates:
            logger.debug(f"collecting coredump via handler '{handler.name}'")
            if handler.collect(output_dir, prefix):
                self._count += 1
                return True
            logger.warning(f"coredump handler '{handler.name}' failed")

        return False

    def reset(self) -> None:
        """Reset the collection counter between test runs."""
        self._count = 0

    @property
    def collected_count(self) -> int:
        """Return the number of coredumps collected this session.

        :return: Non-negative integer count.
        """
        return self._count
