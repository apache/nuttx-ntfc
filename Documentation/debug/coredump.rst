===================
Coredump Collection
===================

What it does
============

A coredump is a snapshot of the device's memory and registers at the
moment it crashed. It's what you load into a debugger afterwards to
see exactly what the code was doing - which function, which
variables, which thread. Without one, a crash in an automated test run
just leaves you with "it crashed" and a log.

Enable with ``debug.coredump.enable: true``. When a test fails, ntfc
picks a device that looks unhealthy (crashed, busy-looping, or dead)
and asks a *backend* to pull a coredump from it. If nothing looks
unhealthy - e.g. a plain assertion in the test itself - it collects
from every product that has coredump collection enabled.

Backends
========

There are five ways to actually get the coredump off the device.
Which one you use depends on what your hardware/setup supports:

* **gdb** - ntfc keeps a GDB session attached to the device for the
  whole test run and tells it to ``gcore`` on failure. Works for QEMU
  and any real hardware with a debug probe (JTAG/SWD) or a running GDB
  stub. See :doc:`gdb` for how this is set up.

* **local_file** - for setups where the coredump ends up as a plain
  file on the host (e.g. QEMU writing straight to the host
  filesystem), ntfc just watches a directory and grabs the newest one.

* **fastboot** - pulls a memory region over USB via the Android
  fastboot protocol, for devices whose bootloader exposes it after a
  crash.

* **syslog** - decodes a coredump that NuttX itself printed to the
  serial console as base64 text (optionally LZF-compressed). Useful
  when there's no debug probe and no fastboot, only a serial port.

* **ymodem** - receives the coredump as a file transferred over the
  serial port using the Ymodem protocol, once NuttX has written it to
  local storage.

============== ======== ==========================================
Backend        Priority Requirements
============== ======== ==========================================
``gdb``        10       ``gdb.enable`` + ``elf_path`` + ``target``/``attach``
``local_file`` 15       ``local_file.core_dir``
``fastboot``   20       ``fastboot.dev_sn``
``syslog``     25       ``syslog.enable``
``ymodem``     30       ``ymodem.serial_port`` + ``sbrb_path``
============== ======== ==========================================

With ``type: auto`` (default) the enabled backend with the lowest
priority value that reports itself available is used - so if you
configure both GDB and fastboot, GDB is tried first. Set ``type`` to a
specific backend name to force just that one.

``limit`` caps the number of coredumps collected in one session
(default: 5) so a device that keeps crashing doesn't fill the disk.

Coredump files are written to::

   <result_dir>/<product-name>/<test-name>.core

If two failing tests share the same terminal name, the later ones get
a numeric suffix (``<test-name>.2.core``, ...) instead of overwriting
the first.

.. note::

   On multi-core (AMP) products, coredump collection only looks at
   core 0 today.

.. _post-mortem-analysis:

Inspecting a coredump
=====================

Once you have a ``.core`` file, load it with the same ELF the session
used::

   gdb-multiarch <elf_path> result/<session>/<product>/<test>.core

   (gdb) bt full
   (gdb) info threads
   (gdb) print g_my_variable

This is the normal way to actually debug the crash - there's no time
pressure and it doesn't disturb a running test session.
