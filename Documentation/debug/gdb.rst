===============
GDB Integration
===============

What it does
============

ntfc can keep a GDB session attached to your device for the whole test
run, so that when a test fails it can pull a coredump on the spot
(the ``gdb`` backend in :doc:`coredump`), and optionally react to
crashes automatically instead of waiting for a test to notice.

Enable with ``debug.gdb.enable: true``. ntfc starts one GDB process per
product after the device is up::

   <gdb_path> -q <elf_path> -ex "set pagination off" -ex "set confirm off"

and connects to it one of two ways:

* **Remote target** (``debug.gdb.target``) - for QEMU or real hardware
  with a debug probe. Set it to the ``host:port`` (or Unix socket path)
  of a GDB stub. For QEMU, add ``-s`` to ``exec_args`` to get a stub on
  ``localhost:1234``.

* **Simulator PID-attach** (``debug.gdb.attach: true``) - for the
  host-based NuttX simulator, where there's no remote stub, just a
  running process. ntfc attaches GDB to it by PID instead. Mutually
  exclusive with ``target``.

  .. note::

     Same-user attach requires ``kernel.yama.ptrace_scope=0`` (or
     ``CAP_SYS_PTRACE``). If your system has it locked down, either
     relax it or set ``gdb.use_sudo: true`` (needs passwordless sudo).

  .. note::

     On ``sim`` a crash is a real OS ``SIGSEGV``, not a NuttX assert.
     Without GDB already attached it kills the process outright (no
     coredump; ntfc reports ``notalive``, not ``crash``). ``attach``
     must be enabled *before* the crash: ``ptrace`` lets an attached
     GDB catch the signal and freeze the process for ``gcore`` instead.

GDB stays attached for the whole session; a plain ``gcore`` writes the
coredump when a test fails.

Automatic coredumps on crash (push model)
=========================================

Normally ntfc only asks GDB for a coredump *after* a test fails -
by then the crash may already be a while in the past. Setting
``debug.gdb.plugin: true`` and ``debug.gdb.auto_breakpoints: true``
flips this around: ntfc plants breakpoints on NuttX's crash and
power-off handlers right after attaching, so GDB generates the
coredump itself the instant the device crashes, before ntfc even
notices. When the failing test runs its own collection, it just picks
up that coredump instead of asking GDB to generate a fresh one.

.. code-block:: yaml

   debug:
     gdb:
       enable: true
       target: "localhost:1234"
       plugin: true
       auto_breakpoints: true

Set ``debug.gdb.mmleak: true`` (requires ``auto_breakpoints``) to also
dump NuttX's memory-leak report on power-off.

The breakpoint's job is to freeze the process for ``gcore``, not to
give you a live session. Inspect the resulting coredump with your own
GDB afterward (:ref:`post-mortem-analysis` in :doc:`coredump`) for the
same backtrace, variables, and threads -- minus the ability to step
forward past the crash.

Other GDB options
=================

* ``gdb.gcore_cmd`` (default ``'gcore'``) - override the corefile
  command, for images that need something different.
* ``gdb.osabi`` - sends ``set osabi <value>`` after attach; ARM NuttX
  targets typically need ``'none'``.
* ``gdb.nx_plugin`` - path to NuttX's own GDB helper
  (``tools/pynuttx/gdbinit.py`` in the NuttX source tree), sourced
  alongside ntfc's plugin.
* ``gdb.setup_cmds`` - raw GDB commands sent right after attach, for
  anything not covered above:

  .. code-block:: yaml

     setup_cmds:
       - 'ntfcautobp bp dump_assert_info ntfcautogcore -d $RESULT_DIR gcore'
       - 'continue'

  Commands can be plain GDB (e.g. ``print my_var``) too, but a plain
  breakpoint does **not** auto-resume - the target stays halted, which
  will make the test time out. Use ``ntfcautobp`` (below) for anything
  meant to run unattended.

The in-GDB plugin
=================

With ``debug.gdb.plugin: true``, ntfc sources a small Python plugin
into the GDB process that provides:

* ``ntfcautobp <bp|wp> <spec> <cmd1>[;<cmd2>...]`` - set a breakpoint
  or watchpoint that runs the given commands when hit, then resumes
  automatically. This is what makes unattended crash handling possible.
* ``ntfcautogcore -d <dir|$RESULT_DIR> [-n <name>] <gcore-cmd>`` -
  generate and verify a coredump.
* ``ntfcmmleak`` - dump NuttX's ``mm leak`` report alongside a
  coredump.
* ``ntfcgdbprefix <command>`` - run a command and quit GDB if it
  fails, so a bad ``setup_cmds`` entry fails fast instead of hanging.

To add your own commands, drop a Python file into
``src/ntfc/debug/gdb/plugin/`` - everything there is imported when
GDB starts.

Manual debugging
================

ntfc owns the GDB process's stdio, and a stub/PID-attach only allows
one client. Disable ``debug.gdb`` and connect your own::

   gdb <elf_path> -ex "target remote localhost:1234"    # QEMU
   gdb <elf_path> -ex "target remote /path/to/socket"   # real hardware

Works for stepping through normal execution. **Does not work for
catching a crash**: on ``sim`` the process is already dead by the time
you attach (nothing caught the signal); on QEMU/hardware the board
resets within seconds of a panic, wiping the crashed state first.
Use ``auto_breakpoints`` to catch a crash instead, then inspect the
coredump it produces (:ref:`post-mortem-analysis`).
