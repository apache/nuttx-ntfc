=======================
Advanced Debug Features
=======================

.. toctree::
   :maxdepth: 1

   coredump
   gdb

Two optional features, both disabled by default and enabled per
product via the ``debug`` section of the product configuration:

* :doc:`coredump` - when a test fails, grab a snapshot of the
  device's memory so you can see what it was doing when it crashed.
* :doc:`gdb` - keep GDB attached to the device throughout the test
  run, so a coredump can be pulled on demand, or generated
  automatically the instant the device crashes.

Device reboot-on-crash (a product going crashed, busy-looping, or
dead is rebooted with retry and back-off) is core ntfc behavior, not
a debug feature -- see the top-level ``config.recovery`` section in
:doc:`../config-yaml`.

Configuration Reference
=======================

.. code-block:: yaml

   product:
     name: "example"
     debug:
       coredump:
         enable: false        # enable coredump collection on test failure
         type: 'auto'         # 'auto', 'gdb', 'fastboot', 'ymodem',
                              # 'local_file' or 'syslog'
         limit: 5             # max coredumps collected per session
       gdb:
         enable: false        # enable the GDB coredump backend
         force_panic: false   # force a panic before coredump collection
         target: ''           # 'target remote' address,
                              # e.g. 'localhost:1234' or '/tmp/gdb.socket'
         gdb_path: 'gdb'      # GDB executable, e.g. 'gdb-multiarch'
         plugin: false        # load the NTFC in-GDB Python plugin
         setup_cmds: []       # raw GDB commands sent after attach
         gcore_cmd: 'gcore'      # corefile command; NuttX images with
                                 # the pynuttx plugin may override this
         nx_plugin: ''           # path to nuttx/tools/pynuttx/gdbinit.py
         osabi: ''               # NuttX arm targets typically need 'none'
         auto_breakpoints: false # plant crash/poweroff breakpoints + continue
         mmleak: false           # mmleak dump on poweroff breakpoint
         attach: false           # PID-attach to the simulator process
         use_sudo: false         # sudo for attach (locked-down ptrace)
       local_file:
         core_dir: ''            # host dir watched for corefiles
         pattern: '*.core'
       syslog:
         enable: false           # decode coredump from serial syslog
       fastboot:
         dev_sn: ''           # fastboot device serial number
         mem_addr: '0x40000000'  # memory dump start address
         mem_size: '0x08000000'  # memory dump size
       ymodem:
         serial_port: ''      # host serial port, e.g. '/dev/ttyUSB0'
         baud_rate: 921600    # baud rate for the transfer
         sbrb_path: ''        # path to the sbrb.py Ymodem receiver

Notes:

* A coredump backend is only registered when its prerequisites are
  configured: GDB needs ``gdb.enable``, a core ``elf_path`` and either
  ``gdb.target`` (remote attach) or ``gdb.attach`` (simulator PID
  attach); ``local_file`` needs ``local_file.core_dir``; fastboot needs
  ``fastboot.dev_sn``; ``syslog`` needs ``syslog.enable``; Ymodem needs
  both ``ymodem.serial_port`` and ``ymodem.sbrb_path``.

See :doc:`coredump` and :doc:`gdb` for details on each feature.
