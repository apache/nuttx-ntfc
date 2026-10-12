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

"""Tests for resource probes."""

import pytest

from ntfc.resmon.base import clean_output, parse_table
from ntfc.resmon.probes import (
    PROBES,
    CpuloadProbe,
    FdsProbe,
    HeapProbe,
    IobProbe,
    MempoolProbe,
    NetProbe,
    TasksProbe,
    make_probes,
)

FREE_HDR = (
    "      total       used       free    maxused    maxfree  nused  nfree"
    " name\n"
)
FREE_UMEM = (
    "   67108864    1787800   65321064    1788496   65257512     66      3"
    " Umem\n"
)
FREE_KMEM = (
    "    1048576     100000     948576     100000     948576     10      1"
    " Kmem\n"
)
FREE_A = FREE_HDR + FREE_UMEM
FREE_B = FREE_HDR + (
    "   67108864    1787900   65320964    1788496   65257512     67      3"
    " Umem\n"
)
FREE_TWO_HEAPS = FREE_HDR + FREE_KMEM + FREE_UMEM

_SIG = "0000000000000000"
PS_A = (
    "  TID   PID  PPID PRI POLICY   TYPE    NPX STATE    EVENT     "
    "SIGMASK            STACK COMMAND\n"
    f"    0     0     0   0 FIFO     Kthread   - Ready              {_SIG}"
    " 0069584 Idle_Task\n"
    f"    1     0     0 224 FIFO     Kthread   - Waiting  Semaphore {_SIG}"
    " 0067456 sim_loop_wq 0x7f36774003f0 0x7f3677400470\n"
    f"    4     4     0 100 FIFO     Task      - Running            {_SIG}"
    " 0067496 nsh_main\n"
)
PS_B = PS_A + (
    f"    5     5     4 100 FIFO     Task      - Waiting  Signal    {_SIG}"
    " 0067480 sh -c sleep\n"
)
PS_SMP = (
    "  TID   PID  PPID CPU PRI POLICY   TYPE    NPX STATE    EVENT     "
    "SIGMASK            STACK COMMAND\n"
    "    0     0     0   0   0 FIFO     Kthread   - Assigned           "
    f"{_SIG} 0002032 CPU0 IDLE\n"
    "    4     4     0   1 100 FIFO     Task      - Running            "
    f"{_SIG} 0003008 nsh_main\n"
)

FD_A = (
    "\n"
    "FD  OFLAGS  TYPE POS       PATH           \n"
    "0   2       1    0         /dev/console  \n"
    "1   2       1    0         /dev/console  \n"
    "3   524288  3    0                       \n"
)
FD_B = FD_A + "4   0       1    0         /tmp/leak     \n"
FD_A_MOVED = FD_A.replace("1   2       1    0  ", "1   2       1    12 ")

IOB_HDR = "    ntotal     nfree     nwait nthrottle\n"
IOB_A = IOB_HDR + "        36        36         0         0\n"
IOB_B = IOB_HDR + "        36        30         0         0\n"

MEMPOOL_A = (
    "                   total    bsize    nused    nfree   nifree  nwaiter\n"
    "       Umem:       4096       32       10       20        0        0\n"
)
MEMPOOL_B = MEMPOOL_A.replace("       10       20", "       12       18")

NET_A = (
    "TCP sl  st flg ref tmr uack nrt   rxsz local_address remote_address\n"
    "     0: 04 000   1   0    0   0   1500 0.0.0.0:80     0.0.0.0:0     \n"
)
NET_B = NET_A + (
    "     1: 04 000   1   3    1   0   1500 10.0.0.2:80    10.0.0.1:5000 \n"
)
NET_A_TICK = NET_A.replace("  1   0    0   0 ", "  1   7    2   0 ")
UDP_EMPTY = "UDP sl  local_address remote_address\n"


class TestCleanOutput:
    def test_strips_echo_and_prompt(self) -> None:
        raw = "free\r\n total used\r\n  1 2\r\nnsh> "
        assert clean_output(raw, "free", "nsh> ") == " total used\n  1 2\n"

    def test_keeps_output_without_echo(self) -> None:
        raw = " total used\n  1 2\nnsh> "
        assert clean_output(raw, "free", "nsh> ") == " total used\n  1 2\n"

    def test_handles_missing_prompt(self) -> None:
        assert clean_output("free\n 1 2", "free", "nsh> ") == " 1 2"

    def test_strips_echo_with_prompt(self) -> None:
        raw = "nsh> free\n 1 2\nnsh> "
        assert clean_output(raw, "free", "nsh> ") == " 1 2\n"

    def test_strips_stale_prompt_before_echo(self) -> None:
        raw = "nsh> \nfree\n 1 2\nnsh> "
        assert clean_output(raw, "free", "nsh> ") == " 1 2\n"


JUNK = "nxposix_spawn_exec: ERROR: exec failed: 2\n"


class TestParseTable:
    def test_junk_before_header_skipped(self) -> None:
        rows = parse_table(JUNK + FD_A, required=["FD", "PATH"])
        assert rows[0]["FD"] == "0"
        assert rows[0]["PATH"] == "/dev/console"

    def test_required_header_missing(self) -> None:
        assert parse_table(JUNK, required=["FD"]) == []

    def test_rows_keyed_by_header(self) -> None:
        rows = parse_table(FREE_A)
        assert rows == [
            {
                "total": "67108864",
                "used": "1787800",
                "free": "65321064",
                "maxused": "1788496",
                "maxfree": "65257512",
                "nused": "66",
                "nfree": "3",
                "name": "Umem",
            }
        ]

    def test_last_column_keeps_spaces(self) -> None:
        rows = parse_table(PS_A)
        assert (
            rows[1]["COMMAND"] == "sim_loop_wq 0x7f36774003f0 0x7f3677400470"
        )

    def test_short_rows_padded(self) -> None:
        rows = parse_table(FD_A)
        assert rows[2]["FD"] == "3"
        assert rows[2]["PATH"] == ""

    def test_explicit_columns(self) -> None:
        rows = parse_table("a b\n1 2\n", columns=["x", "y"], skip=1)
        assert rows == [{"x": "1", "y": "2"}]

    def test_empty(self) -> None:
        assert parse_table("") == []


class TestHeapProbe:
    def test_metadata(self) -> None:
        probe = HeapProbe({})
        assert probe.name == "heap"
        assert probe.commands == ("free",)
        assert ("CONFIG_FS_PROCFS", True) in probe.kconfig
        assert ("CONFIG_FS_PROCFS_EXCLUDE_MEMINFO", False) in probe.kconfig
        assert ("CONFIG_NSH_DISABLE_FREE", False) in probe.kconfig

    def test_junk_before_header(self) -> None:
        probe = HeapProbe({})
        assert probe.parse([JUNK + FREE_A]) == probe.parse([FREE_A])

    def test_no_diff_when_equal(self) -> None:
        probe = HeapProbe({})
        assert probe.diff(probe.parse([FREE_A]), probe.parse([FREE_A])) == []

    def test_used_growth_reported(self) -> None:
        probe = HeapProbe({})
        diff = probe.diff(probe.parse([FREE_A]), probe.parse([FREE_B]))
        assert any("Umem" in d and "used" in d and "+100" in d for d in diff)
        assert any("nused" in d and "+1" in d for d in diff)

    def test_tolerance_hides_small_used_growth(self) -> None:
        probe = HeapProbe({"heap_tolerance": 100})
        diff = probe.diff(probe.parse([FREE_A]), probe.parse([FREE_B]))
        assert not any(" used " in d for d in diff)
        assert any("nused" in d for d in diff)

    def test_shrink_is_not_a_leak(self) -> None:
        probe = HeapProbe({})
        assert probe.diff(probe.parse([FREE_B]), probe.parse([FREE_A])) == []

    def test_multiple_heaps(self) -> None:
        probe = HeapProbe({})
        before = probe.parse([FREE_TWO_HEAPS])
        after = probe.parse(
            [
                FREE_TWO_HEAPS.replace(
                    "100000     948576     100000",
                    "100016     948560     100016",
                )
            ]
        )
        diff = probe.diff(before, after)
        assert len(diff) == 1
        assert diff[0].startswith("Kmem")

    def test_unexpected_output_raises(self) -> None:
        probe = HeapProbe({})
        with pytest.raises(ValueError, match="heap: unexpected output"):
            probe.parse(["nsh: free: command not found\n"])

    def test_new_row_after_is_reported(self) -> None:
        probe = HeapProbe({})
        diff = probe.diff(probe.parse([FREE_A]), probe.parse([FREE_TWO_HEAPS]))
        assert any("Kmem" in d for d in diff)


class TestTasksProbe:
    def test_metadata(self) -> None:
        probe = TasksProbe({})
        assert probe.name == "tasks"
        assert probe.commands == ("ps",)
        assert ("CONFIG_FS_PROCFS_EXCLUDE_PROCESS", False) in probe.kconfig
        assert ("CONFIG_NSH_DISABLE_PS", False) in probe.kconfig

    def test_new_task_reported(self) -> None:
        probe = TasksProbe({})
        diff = probe.diff(probe.parse([PS_A]), probe.parse([PS_B]))
        assert diff == ["new tasks: 5 sh -c sleep"]

    def test_state_change_ignored(self) -> None:
        probe = TasksProbe({})
        after = PS_A.replace("Running ", "Waiting ")
        assert probe.diff(probe.parse([PS_A]), probe.parse([after])) == []

    def test_gone_task_ignored(self) -> None:
        probe = TasksProbe({})
        assert probe.diff(probe.parse([PS_B]), probe.parse([PS_A])) == []

    def test_junk_before_header(self) -> None:
        probe = TasksProbe({})
        assert probe.parse([JUNK + PS_A]) == probe.parse([PS_A])

    def test_blank_event_column(self) -> None:
        probe = TasksProbe({})
        assert ("0", "Idle_Task") in probe.parse([PS_A])

    def test_missing_header_is_empty(self) -> None:
        probe = TasksProbe({})
        assert probe.parse(["nsh: ps: command not found\n"]) == set()

    def test_smp_layout(self) -> None:
        probe = TasksProbe({})
        parsed = probe.parse([PS_SMP])
        assert ("4", "nsh_main") in parsed
        assert ("0", "CPU0 IDLE") in parsed


class TestFdsProbe:
    def test_metadata(self) -> None:
        probe = FdsProbe({})
        assert probe.name == "fds"
        assert probe.commands == ("cat /proc/self/group/fd",)
        assert ("CONFIG_NSH_DISABLE_CAT", False) in probe.kconfig

    def test_new_fd_reported(self) -> None:
        probe = FdsProbe({})
        diff = probe.diff(probe.parse([FD_A]), probe.parse([FD_B]))
        assert diff == ["new fds: 4 1 /tmp/leak"]

    def test_junk_before_header(self) -> None:
        probe = FdsProbe({})
        assert probe.parse([JUNK + FD_A]) == probe.parse([FD_A])

    def test_position_change_ignored(self) -> None:
        probe = FdsProbe({})
        assert probe.diff(probe.parse([FD_A]), probe.parse([FD_A_MOVED])) == []


class TestIobProbe:
    def test_metadata(self) -> None:
        probe = IobProbe({})
        assert probe.name == "iob"
        assert ("CONFIG_MM_IOB", True) in probe.kconfig

    def test_junk_before_header(self) -> None:
        probe = IobProbe({})
        assert probe.parse([JUNK + IOB_A]) == probe.parse([IOB_A])

    def test_free_shrink_reported(self) -> None:
        probe = IobProbe({})
        diff = probe.diff(probe.parse([IOB_A]), probe.parse([IOB_B]))
        assert diff == ["iob nfree 36 -> 30 (-6)"]

    def test_empty_output_raises(self) -> None:
        with pytest.raises(ValueError, match="iob: unexpected"):
            IobProbe({}).parse([""])

    def test_equal_is_clean(self) -> None:
        probe = IobProbe({})
        assert probe.diff(probe.parse([IOB_A]), probe.parse([IOB_A])) == []


class TestMempoolProbe:
    def test_metadata(self) -> None:
        probe = MempoolProbe({})
        assert probe.name == "mempool"
        assert ("CONFIG_MM_HEAP_MEMPOOL", True) in probe.kconfig

    def test_unexpected_output_raises(self) -> None:
        with pytest.raises(ValueError, match="mempool: unexpected"):
            MempoolProbe({}).parse(["nsh: cat: open failed\n"])

    def test_junk_before_header(self) -> None:
        probe = MempoolProbe({})
        assert probe.parse([JUNK + MEMPOOL_A]) == probe.parse([MEMPOOL_A])

    def test_nused_growth_reported(self) -> None:
        probe = MempoolProbe({})
        diff = probe.diff(probe.parse([MEMPOOL_A]), probe.parse([MEMPOOL_B]))
        assert diff == ["Umem nused 10 -> 12 (+2)"]


class TestNetProbe:
    def test_metadata(self) -> None:
        probe = NetProbe({})
        assert probe.name == "net"
        assert probe.commands == ("cat /proc/net/tcp", "cat /proc/net/udp")
        assert ("CONFIG_NET", True) in probe.kconfig

    def test_new_connection_reported(self) -> None:
        probe = NetProbe({})
        before = probe.parse([NET_A, UDP_EMPTY])
        after = probe.parse([NET_B, UDP_EMPTY])
        assert probe.diff(before, after) == [
            "new net: 10.0.0.2:80 10.0.0.1:5000"
        ]

    def test_counters_ignored(self) -> None:
        probe = NetProbe({})
        before = probe.parse([NET_A, UDP_EMPTY])
        after = probe.parse([NET_A_TICK, UDP_EMPTY])
        assert probe.diff(before, after) == []


class TestCpuloadProbe:
    def test_metadata(self) -> None:
        probe = CpuloadProbe({})
        assert probe.name == "cpuload"
        assert ("CONFIG_SCHED_CPULOAD", True) in probe.kconfig

    def test_above_limit_reported(self) -> None:
        probe = CpuloadProbe({"cpuload_max": 10})
        diff = probe.diff(probe.parse(["  1.0%\n"]), probe.parse([" 57.5%\n"]))
        assert diff == ["cpuload 57.5% > 10%"]

    def test_below_limit_clean(self) -> None:
        probe = CpuloadProbe({"cpuload_max": 10})
        assert (
            probe.diff(probe.parse([" 1.0%\n"]), probe.parse([" 9.9%\n"]))
            == []
        )

    def test_unparsable_is_clean(self) -> None:
        probe = CpuloadProbe({})
        assert probe.diff(probe.parse(["x\n"]), probe.parse(["garbage"])) == []


class TestRegistry:
    def test_all_probes_registered(self) -> None:
        assert set(PROBES) == {
            "heap",
            "tasks",
            "fds",
            "iob",
            "mempool",
            "net",
            "cpuload",
        }

    def test_make_probes_keeps_order(self) -> None:
        probes = make_probes(["tasks", "heap"], {})
        assert [p.name for p in probes] == ["tasks", "heap"]

    def test_make_probes_unknown_name(self) -> None:
        with pytest.raises(ValueError, match="unknown resource probe"):
            make_probes(["nope"], {})
