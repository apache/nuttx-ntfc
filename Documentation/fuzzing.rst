====================
Kconfig Fuzzing
====================

NTFC can fuzz NuttX Kconfig options on top of a known-good base configuration
to surface three classes of problem:

* **Build breaks** -- an option that no longer compiles (for example a now
  shared ``CONFIG_STM32_*`` option enabled on a family whose driver was never
  ported).
* **Broken features at runtime** -- an option (or combination) that builds but
  makes ``ostest`` crash, hang, or fail.
* **Memory cost** -- the flash/RAM footprint an option or feature adds.

The fuzzer generates many candidate configurations from one base config and
drives each through NTFC's existing build (:class:`~ntfc.builder.NuttXBuilder`)
and device (sim / QEMU / serial) layers.  A candidate is simply the base
``defconfig`` plus a set of Kconfig overrides -- the same ``kv`` mechanism NTFC
already uses -- so no transient board directory is created.

Two kinds of config
===================

The fuzzer separates *what to fuzz* from *where to run it*:

* The **fuzz config** is fuzzer-only: feature, surface, strategy, mock,
  workers/jobs.  It has no device/board/flash concepts.
* The **target** is a normal NTFC config (device, board defconfig, QEMU
  ``exec_args``, serial port, ``flash``/``reboot``).  It is reused as-is for
  sim, QEMU, or real hardware.

How many configs a run needs depends on whether it boots a device:

.. list-table::
   :header-rows: 1

   * - Feature
     - Boots a device?
     - Configs
   * - ``build``
     - no -- only compiles
     - **1** -- the fuzz config (it names ``board`` + ``tree``)
   * - ``mem``
     - no -- compiles + sizes ELF
     - **1** -- the fuzz config
   * - ``ostest``
     - yes -- runs the target
     - **2** -- fuzz config **+** NTFC target (``--confpath``)

Usage
=====

.. code-block:: bash

   # only discover and print the fuzz surface (no build):
   ntfc fuzz --campaign config/fuzz/build-stm32.yaml --list

   # print the planned candidate matrix (no build; for ostest this works
   # without --confpath -- the matrix depends only on the fuzz config):
   ntfc fuzz --campaign config/fuzz/build-stm32.yaml --dry-run

   # build-break sweep (one config -- board + tree are in the fuzz config):
   ntfc fuzz --campaign config/fuzz/build-stm32.yaml

   # memory footprint report (one config):
   ntfc fuzz --campaign config/fuzz/mem-sim.yaml

   # ostest sweep (TWO configs: fuzz config + NTFC target):
   ntfc fuzz --campaign config/fuzz/ostest-sim.yaml \
             --confpath config/nuttx-sim-nsh.yaml

The report (``fuzz-report.txt`` and ``fuzz-report.json``) is written to the
NTFC session directory, beside normal test results, and the full build/run log
of every non-pass candidate is saved next to the build.  The exit code is
non-zero if any candidate did not pass.

Requirements
============

* ``kconfiglib`` (installed as an NTFC dependency) -- Kconfig parsing.
* ``cmake`` and ``ninja`` -- the build backend, as for any NTFC build.
* A ``tree`` dir containing sibling ``nuttx/`` and ``apps/`` checkouts.

Fuzz config
===========

A fuzz config is a flat, fuzzer-only YAML file.

.. code-block:: yaml

   # fuzz-build.yaml -- a build-break sweep (build/mem carry their own target)
   feature: build             # build | ostest | mem
   arch: stm32                # arch profile (skip/mock/board-required rules)

   board: nucleo-h563zi:nsh   # build/mem only: board:config to build
   tree: ./external           # build/mem only: dir with nuttx/ and apps/

   surface:                   # WHAT to fuzz -- choose one style:
     scope: [arch]            #   by subsystem (see "Scopes" below)
     # symbols: [NET_TCP, FS_FAT]   # or explicit symbol names
     # features:                    # or named feature groups
     #   net: [CONFIG_NET, CONFIG_NETDEV_LATEINIT]
     include_choices: false

   strategy:                  # HOW to combine
     mode: single             # single | random | pairs | marginal | full
     limit: 10                # cap the candidate count (0/absent = no cap)
     rounds: 20               # random mode
     size: 4                  # random mode
     seed: 0                  # random mode
     minimize: true           # delta-debug failing combinations

   mock: true                 # build-validation mock mode
   require: [CONFIG_SCHED_HPWORK]   # options enabled in every build
   timeout: 600               # ostest per-run seconds

   parallel: true             # fuzzer orchestration
   workers: 4                 # candidates built/run concurrently
   jobs: 4                    # ninja jobs per build

For ``ostest`` the ``board`` and ``tree`` keys are omitted -- the target
(board, device, run parameters) comes entirely from the NTFC config passed with
``--confpath``.

``feature``
-----------

Which of the three capabilities to run:

* ``build`` -- build each candidate; report ``pass`` / ``build-fail`` (and
  ``pass-mocked`` when ``mock`` is set).
* ``ostest`` -- build and run each candidate on the ``--confpath`` target's
  device, classifying ``pass`` / ``test-fail`` / ``crash`` / ``timeout`` and
  delta-debugging failing combinations to a minimal set.
* ``mem`` -- build the base and per-feature variants and diff the linked image
  sizes into a flash/RAM cost table.

``surface``
-----------

Selects the fuzz surface, in one of three styles:

* ``scope`` -- a list of subsystem names (see `Scopes`_).
* ``symbols`` -- explicit Kconfig symbol names (without the ``CONFIG_``
  prefix).
* ``features`` -- named groups of options treated as single units
  (``mem`` / ``ostest``).

``include_choices`` (default ``false``) also fuzzes members of ``choice``
blocks.

``strategy``
------------

* ``mode`` -- ``single`` (one option at a time), ``random`` (random subsets),
  or the systematic modes ``marginal`` / ``pairs`` / ``full``.
* ``limit`` -- cap the number of candidates (the first N of the sweep); use it
  to keep a large discovered surface bounded.  Preview the matrix with
  ``--dry-run``.  ``mem`` uses ``max_builds`` (default 64) instead.
* ``rounds`` / ``size`` / ``seed`` -- random-mode controls (seed makes a run
  reproducible).
* ``minimize`` (default ``true``) -- delta-debug each failing combination to
  the smallest subset that still fails.

Data files
==========

Everything the fuzzer "knows" that changes over time lives in editable YAML
data files under ``src/ntfc/fuzz/data/`` (shipped as package data,
overridable).  Maintaining the fuzz surface never requires editing code.

``arch-profiles.yaml``
   Per-architecture rules: which Kconfig files form the arch surface
   (``symbol_path``), which symbol prefixes are never toggled
   (``skip_prefixes``), which build-error identifiers are board-supplied and
   therefore mockable (``mockable_prefixes`` / ``mockable_suffixes``), and any
   arch-specific board-config-requirement patterns (``extra_board_required``).
   Add a new architecture by adding an entry -- no code change.

``scopes.yaml``
   The subsystem vocabulary: a name (``net``, ``fs``, ``usb``, ``drivers``,
   ``kernel`` ...) mapped to a regex matched against a symbol's defining
   Kconfig file path.  Add a subsystem with one line.

``patterns.yaml``
   The classification regex tables: ``board_required`` (unmet board
   prerequisites, not code bugs), ``config_required`` (Kconfig dependency
   problems), ``build_error`` (log excerpting), and ``ostest_exit`` / ``crash``
   (runtime classification, complementing the device layer's own crash
   detection).

.. _scopes:

Scopes
------

``scope`` accepts ``arch`` (the arch profile's own surface), ``all`` (the whole
tree), or any named subsystem from ``scopes.yaml``, comma-separated -- for
example ``[net, fs, audio]``.  Discovery only returns options that are actually
settable from the chosen base, so to fuzz a subsystem deeply pick a base config
that already enables its root.  Beware of subsystems gated behind a single
``menuconfig``: on a base config that does not enable it, a scope like
``[can]`` collapses to just that one root option (everything below it is not
yet settable) and the sweep degenerates to a single candidate.  Check the
surface first with ``--list``; ``arch`` on a chip base config is usually the
richest build-break surface.

Mock mode
=========

Many peripherals fail to build only because the board's ``board.h`` does not
define the pin mapping or geometry constants for a peripheral it never wires
(``'GPIO_CAN2_RX' undeclared``, ``#error BOARD_LTDC_WIDTH must be defined``).
With ``mock: true`` the fuzzer reads those errors, synthesises just the missing
*board-supplied* constants (using gcc's own "did you mean" suggestion for pin
alternatives), injects them into the build's generated ``config.h`` -- touching
no source -- and rebuilds.  Only an allowlist of board-constant prefixes is
mocked, so genuine code bugs still fail the build.  Results split into
``pass-mocked`` (the arch path compiles once board pins are provided) and
``build-fail`` (a real code bug).

Mocked builds validate **compilation**, not runtime correctness.

Caveats
=======

* The ostest sweep boots the base config to NSH, runs the ``ostest`` builtin
  over the device layer, and treats the ``ostest_main: Exiting with status N``
  line as authoritative (0 -> pass, else test-fail).  The **simulator is the
  natural first target** and works well; note the full ostest suite is not
  real-time under the sim and runs the whole suite each candidate, so a single
  run takes a few minutes (≈3 min on the ``sim:nsh`` baseline) -- set
  ``timeout`` accordingly and raise ``workers`` to parallelise.  QEMU and real
  serial targets work the same way via ``device: qemu`` / ``serial``.  The full
  console output of every non-pass run is saved next to the build for
  inspection.
* ``mem`` reports the static footprint of the linked image; it does not model
  runtime heap or stack.
