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

"""Fake NuttX target with its NSH console on a UDP netdev console."""

import socket
import sys

host = ("127.0.0.1", int(sys.argv[1]))
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("127.0.0.1", 0))

# output on the pty is not the console
print("netconsole target up", flush=True)

sock.sendto(b"\nNuttShell (NSH)\nnsh> ", host)
line = b""
while True:
    line += sock.recv(4096)
    while b"\n" in line:
        cmd, line = line.split(b"\n", 1)
        out = cmd + b"\n"
        if cmd.strip() == b"hello":
            out += b"Hello, World!\n"
        elif cmd and cmd[0] == 0x03:
            out = b"^C\n"
        sock.sendto(out + b"nsh> ", host)
