====================================
Products Configuration (config.yaml)
====================================

This file defines device-under-test (DUT) setup and global configuration.

**Structure for single DUT:**

.. code-block:: yaml

   config:
     # global configuration

   product:
     name: "product-name"     # Product identifier
     cores:                   # List of product cores
       core0:                 # Core0 entry
         name: 'core0-name'
         device: 'sim|qemu|serial'
         # Device-specific configuration

       core1:                 # Core1 entry
         name: 'core1-name'
         device: 'sim|qemu|serial'
         # Device-specific configuration


**Structure for many DUT:**

.. code-block:: yaml

   config:
     # global configuration

   product0:
     name: "product0-name"    # Product 0 identifier
     cores:
       core0:
         name: 'core-name'
         device: 'sim|qemu|serial'
         # Device-specific configuration

   product1:
     name: "product1-name"    # Product 1 identifier
     cores:
       core0:
         name: 'core-name'
         device: 'sim|qemu|serial'
         # Device-specific configuration


Platform Types
==============

NTFC supports two multi-core platform types:

**AMP (Asymmetric Multi-Processing)** - Default mode

In AMP mode, each core has its own device instance. This is managed by
the :class:`ntfc.cores.CoresHandler`. Tests are executed on
specific cores based on the core configuration. Each core operates independently
with its own memory space and execution context.

.. code-block:: yaml

   product:
     name: "product-name"
     platform: "amp"              # Optional, defaults to "amp"
     cores:
       core0:
         name: 'main'
         device: 'qemu'
         # ... core0 configuration
       core1:
         name: 'cpu1'
         device: 'qemu'
         # ... core1 configuration

Use AMP when:

- Each core has its own device/serial interface
- Cores run independently
- Testing different firmware images on each core

**Build/flash-only auxiliary cores**

A core can be marked as build/flash-only with ``flash_only: true``. NTFC will
still build and flash that core, but it will not:

- wait for that core to boot,
- validate ``ntfc.yaml`` Kconfig requirements on it,
- collect logs from it,
- send test commands to it, or
- include it in reboot/heartbeat/test orchestration.

This is useful when one tested core depends on companion firmware running on
another core, but only the tested core should participate in NTFC runtime
checks.

.. code-block:: yaml

   product:
     name: "product-name"
     platform: "amp"
     cores:
       core0:
         name: 'cpuapp'
         device: 'serial'
         exec_path: '/dev/ttyACM0'
         exec_args: '115200,n,8,1'
         # core0 is the tested core

       core1:
         name: 'cpunet'
         device: 'serial'
         exec_path: '/dev/ttyACM1'
         exec_args: '115200,n,8,1'
         flash_only: true
         # core1 is built/flashed only

**SMP (Symmetric Multi-Processing)**

In SMP mode, all cores share the same device instance, coordinated by
the :class:`ntfc.cores.CoresHandler`. NTFC automatically
switches between cores during test execution using the NuttX ``cu`` (call up)
command. Tests are parametrized to run on each core sequentially.

.. code-block:: yaml

   product:
     name: "product-name"
     platform: "smp"              # Enable SMP mode
     cores:
       core0:
         name: 'main'
         device: 'serial'
         exec_path: '/dev/ttyUSB0'
         exec_args: '115200,n,8,1'
         # ... core0 configuration
       core1:
         name: 'cpu1'
         # core1 shares the same device in SMP mode
       core2:
         name: 'cpu2'
         # core2 shares the same device in SMP mode

Use SMP when:

- Multiple cores share the same device/serial interface
- Testing SMP NuttX configuration
- Need to run tests on different cores through a single interface

**Running tests on specific cores (SMP):**

When SMP mode is enabled, you can specify which cores to run tests on using
the ``--run_in_cores`` option:

.. code-block:: bash

   python -m ntfc test --run_in_cores=main,cpu1,cpu2

This will parametrize tests to run on each specified core. NTFC automatically
handles core switching before and after each test execution.

Device Types
============

Simulator (sim)
---------------

This device type is implemented in :class:`ntfc.device.sim.DeviceSim`.

.. code-block:: yaml

   cores:
     core0:
       name: 'main'
       device: 'sim'
       exec_path: ''   # empty for sim
       exec_args: ''   # empty for sim

QEMU
----

This device type is implemented in :class:`ntfc.device.qemu.DeviceQemu`.

.. code-block:: yaml

   cores:
     core0:
       name: 'main'
       device: 'qemu'
       exec_path: 'qemu-system-arm'
       exec_args: '-cpu cortex-a7 -nographic -machine virt'

Common QEMU executables: ``qemu-system-arm``, ``qemu-system-aarch64``,
``qemu-system-i386``, ``qemu-system-x86_64``, ``qemu-system-riscv64``

At default NTFC automatically add the ``-kernel path_to_elf_image`` option
to ``exec_args``. You can also add your custom boot parameter with
``$IMAGE_ELF``, where ``$IMAGE_ELF`` will be replaced with the path to the ELF.

Serial Device
-------------

This device type is implemented in :class:`ntfc.device.serial.DeviceSerial`.
For real hardware with UART communication:

.. code-block:: yaml

   cores:
     core0:
       name: 'main'
       device: 'serial'
       exec_path: '/dev/ttyACM0'
       exec_args: '115200,n,8,1'
       defconfig: 'boards/arm/stm32h7/nucleo-h743zi/configs/ntfc'
       flash: 'st-flash write $IMAGE_BIN 0x08000000'
       reboot: 'st-flash reset'
       poweroff: ''

**Serial Settings Format:** ``BAUDRATE,PARITY,DATABITS,STOPBITS``

- BAUDRATE: 9600, 19200, 38400, 57600, 115200, etc.
- PARITY: 'n' (None), 'e' (Even), 'o' (Odd), 'm' (Mark), 's' (Space)
- DATABITS: 5, 6, 7, or 8
- STOPBITS: 1, 1.5, or 2

Configuration Approaches
========================

**Auto-build:**

NTFC can automatically builds NuttX with CMake when core configuration has:

.. code-block:: yaml

   defconfig: 'path/to/nuttx/defconfig'

You can specify additional defines passed to CMake with:

.. code-block:: yaml

   dcmake:
     DEFINE1: "VALUE1"
     DEFINE2: "VALUE2"

``dcmake`` uses the same YAML mapping style as ``build_env`` (``KEY: VALUE``).

You can also pass environment variables to the build process (CMake configure
and ``cmake --build``), for example to select a specific compiler version:

.. code-block:: yaml

   config:
     cwd: './external'
     build_dir: './build'
     build_env:
       CC: gcc-14
       CXX: g++-14

   product:
     name: "product"
     cores:
       core0:
         name: 'main'
         device: 'serial'
         defconfig: 'boards/arm/stm32h7/nucleo-h743zi/configs/ntfc'
         build_env:              # optional per-core override
           CXX: g++-14

You can override Kconfig values in the generated ``.config`` before building
with global ``config.kv`` entries and optional per-core ``kv`` entries:

.. code-block:: yaml

   config:
     cwd: './external'
     build_dir: './build'
     kv:
       CONFIG_DEBUG_FEATURES: "y"
       CONFIG_IDLETHREAD_STACKSIZE: "4096"
       CONFIG_BOARD_CUSTOM_NAME: "my-board"

   product:
     name: "product"
     cores:
       core0:
         kv:
           CONFIG_DEBUG_FEATURES: "n"     # overrides global
           CONFIG_BOARD_CORE0_ONLY: "y"   # core-only option

Global ``config.kv`` values are applied first, then ``cores.<core>.kv``.
Per-core entries override the same keys from ``config.kv``.

JSON session ``args.kv`` (if provided) overrides the global ``config.kv``
layer, while per-core ``kv`` still keeps highest priority.

``kv`` uses the same YAML/JSON mapping style as ``dcmake`` and ``args``
(``KEY: VALUE``).

These overrides are applied after CMake configure creates ``.config`` and
before ``cmake --build`` starts.

Build directory and path to NuttX repositories must be specified in global
configuration section:

.. code-block:: yaml

  config:
    cwd: './external'
    build_dir: './build'     # Build output directory
    build_env:               # Optional env vars for cmake configure/build
      CC: gcc-14
      CXX: g++-14
    kv:                      # Optional Kconfig overrides before build
      CONFIG_EXAMPLE: "y"
      CONFIG_NAME: "value"

Use when:

- Fresh build needed for each test run
- Development/testing workflow
- Easier to use

**Pre-compiled ELF:**

Use existing NuttX binary and skip build step when product configuration has:

.. code-block:: yaml

   elf_path: './external/nuttx/nuttx'
   conf_path: './external/nuttx/.config'

Use when:

- Faster repeated test runs
- Pre-built test images available
- CI environments with cached binaries

**Hardware Control (real hardware):**

Automate firmware deployment and device control:

- ``flash``: System command executed before tests
- ``reboot``: System command for hardware reboot of the device
- ``poweroff``: System command for hardware poweroff of the device

Flash command can use special tags that are handled by NTFC:

- ``$IMAGE_BIN`` is replaced by path to ``nuttx.bin``.
- ``$IMAGE_HEX`` is replaced by path to ``nuttx.hex``.

Example usage with ``st-flash`` tool:

.. code-block:: yaml

   flash: 'st-flash write $IMAGE_BIN 0x08000000'
   reboot: 'st-flash reset'
   poweroff: 'st-flash reset'

**Hard vs Soft reboot/poweroff:**

The ``reboot()`` and ``poweroff()`` device methods support two modes,
selectable via the ``hard`` parameter (default ``True``):

- **Hard mode** (``hard=True``): Uses hardware-level control.

  - *Serial devices*: runs the ``reboot`` / ``poweroff`` system command from
    config (e.g. ``st-flash reset``). Returns ``False`` when no command is
    configured.
  - *Host devices (sim/qemu)*: restarts the emulator process entirely via
    ``_dev_reopen()``.

- **Soft mode** (``hard=False``): Sends the OS shell command (``reboot`` or
  ``poweroff``) to the device via the serial/shell interface. Always returns
  ``True`` after sending the command.

Product Configuration Fields
============================

These fields are parsed by :class:`ntfc.productconfig.ProductConfig`.

.. list-table::
   :header-rows: 1

   * - Field
     - Description
   * - ``name``
     - Product identifier
   * - ``platform``
     - Platform type: ``amp`` (default) or ``smp``.
       See `Platform Types`_ section
   * - ``cores``
     - List of product cores (core0, core1, etc.)
   * - ``ignored_cores``
     - (Optional) List of core names to skip when collecting core topology
       info via ``get_core_info``. Defaults to ``["dsp"]``

Core Configuration Fields
=========================

These fields are parsed by :class:`ntfc.coreconfig.CoreConfig`.

.. list-table::
   :header-rows: 1

   * - Field
     - Description
   * - ``name``
     - Human-readable core name
   * - ``device``
     - Device type: ``sim``, ``qemu``, or ``serial``
   * - ``exec_path``
     - QEMU executable name or serial port device (``/dev/ttyACM0``, ``COM1``,
       etc.)
   * - ``exec_args``
     - QEMU arguments or serial settings
   * - ``defconfig``
     - Path to NuttX defconfig (auto-build)
   * - ``elf_path``
     - Path to ELF binary (pre-compiled)
   * - ``conf_path``
     - Path to NuttX ``.config`` file (pre-compiled)
   * - ``flash``
     - System command to flash firmware (work in progress)
   * - ``reboot``
     - System command for hardware reboot of the device (serial only)
   * - ``poweroff``
     - System command for hardware poweroff of the device (serial only)
   * - ``flash_only``
     - Build/flash this core but exclude it from runtime test orchestration:
       no boot checks, no requirement validation, no logs, and no command
       execution against it
   * - ``dcmake``
     - Defines passed to CMake build (YAML mapping syntax, e.g.
       ``FEATURE_X: ON``)
   * - ``build_env``
     - Environment variables passed to CMake configure/build for this core.
       Overrides ``config.build_env`` keys when both are set
   * - ``kv``
     - Per-core Kconfig overrides applied before build. Overrides matching
       keys from global ``config.kv``
