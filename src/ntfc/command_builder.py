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

"""CommandBuilder: encodes sendCommand arguments into device-ready bytes."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from ntfc.type_defs import PatternLike


@dataclass
class EncodedCommand:
    """Encoded command ready for device transmission.

    :param cmd: Command encoded as bytes.
    :param pattern: Expected-response pattern encoded as bytes.
    :param fail_pattern: Optional failure pattern encoded as bytes.
    """

    cmd: bytes
    pattern: bytes
    fail_pattern: Optional[bytes]


class CommandBuilder:
    """Translates public sendCommand parameters into device-ready bytes.

    All encoding logic that previously lived as private helpers on
    ``ProductCore`` is collected here so it can be tested independently
    and reused across methods.
    """

    def __init__(self, prompt: bytes, no_cmd: str) -> None:
        """Initialize CommandBuilder.

        :param prompt: Device prompt bytes (e.g. ``b"nsh> "``).
        :param no_cmd: String the device prints when a command is not found.
        """
        self._prompt = prompt
        self._no_cmd = no_cmd

    def build(
        self,
        cmd: str,
        expects: Optional[Union[str, List[str]]],
        args: Optional[Union[str, List[str]]],
        flag: str,
        match_all: bool,
        regexp: bool,
        fail_pattern: Optional[Union[str, List[str]]],
    ) -> EncodedCommand:
        """Build an :class:`EncodedCommand` for sendCommand.

        :param cmd: Raw command string.
        :param expects: Expected output string(s), or ``None`` to fall back
            to the prompt pattern.
        :param args: Extra arguments appended to *cmd*.
        :param flag: Override prompt string used when *expects* is ``None``.
        :param match_all: ``True`` — all expects must match (AND);
            ``False`` — any one suffices (OR).
        :param regexp: ``True`` — treat expects/fail_pattern as raw regexes;
            ``False`` — treat them as literal strings (auto-escaped).
        :param fail_pattern: Pattern(s) whose presence signals failure.
        :return: :class:`EncodedCommand` with all fields populated.
        """
        cmd_str = self._prepare_command(cmd, args)
        pattern = self._prepare_pattern(
            cmd_str, expects, flag, match_all, regexp
        )
        cmd_bytes, pattern_bytes = self._encode_for_device(cmd_str, pattern)
        fail_bytes = (
            self._build_fail_pattern_bytes(fail_pattern, regexp)
            if fail_pattern
            else None
        )
        return EncodedCommand(cmd_bytes, pattern_bytes, fail_bytes)

    def build_raw(
        self,
        cmd: str,
        pattern: "Optional[PatternLike]",
        args: Optional[Union[str, List[str]]],
        fail_pattern: "Optional[PatternLike]",
    ) -> EncodedCommand:
        """Build an :class:`EncodedCommand` for sendCommandReadUntilPattern.

        :param cmd: Raw command string.
        :param pattern: Explicit pattern to match, or ``None`` to fall back
            to the default prompt pattern.
        :param args: Extra arguments appended to *cmd*.
        :param fail_pattern: Pattern(s) whose presence signals failure.
        :return: :class:`EncodedCommand` with all fields populated.
        """
        cmd_str = self._prepare_command(cmd, args)
        pat = self._default_prompt_pattern(cmd_str) if not pattern else pattern
        cmd_bytes, pattern_bytes = self._encode_for_device(cmd_str, pat)
        fail_bytes = (
            self._encode_fail_pattern(fail_pattern) if fail_pattern else None
        )
        return EncodedCommand(cmd_bytes, pattern_bytes, fail_bytes)

    def encode_pattern(self, pattern: "PatternLike") -> bytes:
        """Encode a pattern to bytes.

        :param pattern: A str, bytes, or list thereof.
        :return: Bytes representation of *pattern*.
        """
        _, pattern_bytes = self._encode_for_device("", pattern)
        return pattern_bytes

    def encode_fail_pattern(self, fail_pattern: "PatternLike") -> bytes:
        """Encode a fail pattern to bytes.

        :param fail_pattern: A str, bytes, or list thereof.
        :return: Bytes OR-regex ready for ``re.search``.
        """
        return self._encode_fail_pattern(fail_pattern)

    def _prepare_command(
        self, cmd: str, args: Optional[Union[str, List[str]]]
    ) -> str:
        """Ensure command is valid and include arguments.

        :param cmd: Base command string.
        :param args: Extra arguments to append, or ``None``.
        :raises ValueError: If *cmd* is empty or falsy.
        :return: Final command string.
        """
        if not cmd:
            raise ValueError("Command cannot be empty.")
        if args:
            if not isinstance(args, (list, tuple)):
                args = [args]
            cmd = f"{cmd} {' '.join(args)}"
        return cmd

    def _prepare_pattern(
        self,
        cmd: str,
        expects: Optional[Union[str, List[str]]],
        flag: str,
        match_all: bool,
        regexp: bool,
    ) -> str:
        """Build a single regex pattern string.

        :param cmd: Command string (used to build the not-found alternative).
        :param expects: Expected output(s), or ``None``.
        :param flag: Override prompt; used when *expects* is ``None``.
        :param match_all: AND vs OR semantics for multiple expects.
        :param regexp: Whether expects are raw regexes.
        :return: Combined regex pattern string.
        """
        if expects:
            expects_list = (
                expects if isinstance(expects, (list, tuple)) else [expects]
            )
            pattern = self._build_expect_pattern(
                expects_list, match_all, regexp
            )
        else:
            pattern = self._default_prompt_pattern(cmd, flag)

        notfound_pattern = re.escape(f"{cmd.split(' ')[0]}: {self._no_cmd}")
        return f"(?s)({pattern}|{notfound_pattern})"

    def _build_expect_pattern(
        self, expects: List[str], match_all: bool, regexp: bool
    ) -> str:
        """Return a single regex string from a list of expected strings.

        :param expects: List of expected output strings.
        :param match_all: ``True`` for AND (lookahead), ``False`` for OR.
        :param regexp: ``True`` — treat items as raw regexes; ``False`` —
            auto-escape them.
        :return: Combined regex string.
        """
        items = expects if regexp else [re.escape(e) for e in expects]

        if match_all:
            # Anchor the lookaheads so the engine evaluates them once from
            # the start of the buffer. Unanchored, re.search retries them
            # at every position and each scans to the end: quadratic in
            # the buffer size, tens of seconds on a 100 KB console dump.
            return "^" + "".join(f"(?=.*{item})" for item in items)
        return rf"({'|'.join(items)})"

    def _default_prompt_pattern(self, cmd: str, flag: str = "") -> str:
        """Return the prompt-based fallback pattern.

        :param cmd: Command string (used in negative lookahead).
        :param flag: Override prompt string; falls back to stored prompt.
        :return: Regex string that matches the prompt but not the echoed cmd.
        """
        prompt = flag if flag else self._prompt.decode()
        if cmd not in ["\n"]:
            return f"{re.escape(prompt)}(?!.*{cmd})"
        return re.escape(prompt)

    def _encode_for_device(
        self, cmd: str, pattern: "PatternLike"
    ) -> Tuple[bytes, bytes]:
        """Encode command and pattern to bytes, merging lists if needed.

        :param cmd: Command string to encode.
        :param pattern: Pattern as str, bytes, bytearray, or list thereof.
        :return: Tuple of (cmd_bytes, pattern_bytes).
        """
        cmd_bytes = cmd.encode("utf-8")

        if isinstance(pattern, list):
            pattern_str = "".join(
                (
                    p.decode("utf-8")
                    if isinstance(p, (bytes, bytearray))
                    else str(p)
                )
                for p in pattern
            )
            pattern_bytes = pattern_str.encode("utf-8")
        elif isinstance(pattern, (bytes, bytearray)):
            pattern_bytes = bytes(pattern)
        else:
            pattern_bytes = str(pattern).encode("utf-8")

        return cmd_bytes, pattern_bytes

    def _build_fail_pattern_bytes(
        self,
        fail_pattern: Union[str, List[str]],
        regexp: bool,
    ) -> bytes:
        """Encode fail_pattern strings into a single bytes OR-regex.

        :param fail_pattern: One or more literal/regex patterns.
        :param regexp: If ``False``, each pattern is escaped before joining.
        :return: Bytes OR-regex ready for ``re.search``.
        """
        items = (
            fail_pattern if isinstance(fail_pattern, list) else [fail_pattern]
        )
        if not regexp:
            items = [re.escape(p) for p in items]
        return "|".join(f"(?:{p})" for p in items).encode("utf-8")

    def _encode_fail_pattern(
        self,
        fail_pattern: "PatternLike",
    ) -> bytes:
        """Encode fail_pattern (str/bytes/list) into a single bytes OR-regex.

        Unlike :meth:`_build_fail_pattern_bytes` this method accepts bytes
        items and does not apply regexp escaping — patterns are used as-is.

        :param fail_pattern: One or more regex patterns indicating failure.
        :return: Bytes OR-regex ready for ``re.search``.
        """
        fp_list: List[Union[str, bytes]] = (
            fail_pattern if isinstance(fail_pattern, list) else [fail_pattern]
        )
        decoded = [
            p.decode("utf-8") if isinstance(p, bytes) else p for p in fp_list
        ]
        return "|".join(f"(?:{p})" for p in decoded).encode("utf-8")
