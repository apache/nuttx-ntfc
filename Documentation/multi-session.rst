=======================
Multi-Session Execution
=======================

NTFC can run multiple test sessions from a single command using a manifest
YAML file.  Instead of invoking ``ntfc test`` once per configuration, you
describe all sessions in a manifest and NTFC handles building, scheduling,
and unified reporting automatically.

.. code-block:: bash

   python -m ntfc test --manifest manifest.yaml

The ``--manifest`` option is mutually exclusive with ``--confpath`` /
``--testpath``.  When a manifest is provided, NTFC ignores those options and
operates entirely from the manifest file.

Manifest Format
===============

A manifest file has two top-level keys:

.. code-block:: yaml

   options:
     fail_fast: false
     parallel: false

   sessions:
     - name: session-a
       confpath: path/to/config-a.yaml
       testpath: path/to/tests-a
     - name: session-b
       confpath: path/to/config-b.yaml
       testpath: path/to/tests-b
       resources: [vcan0]

``options``
-----------

Optional mapping controlling execution behavior:

* ``fail_fast`` (bool, default ``false``) -- stop after the first session
  failure.  In parallel mode an event is set so pending sessions exit early.
* ``parallel`` (bool, default ``false``) -- enable resource-aware parallel
  scheduling (see below).

``sessions``
------------

A non-empty list of session entries.  Each entry accepts the following keys:

.. list-table::
   :header-rows: 1
   :widths: 20 10 70

   * - Key
     - Required
     - Description
   * - ``name``
     - yes
     - Unique session identifier.  Must not be duplicated.
   * - ``confpath``
     - yes
     - Path to the product configuration YAML for this session.
   * - ``testpath``
     - yes
     - Path to the test cases directory.
   * - ``resources``
     - no
     - List of host resource tags used by this session (e.g. ``[vcan0]``).
   * - ``exitonfail``
     - no
     - Override per-session exit-on-fail behavior (bool).
   * - ``loops``
     - no
     - Number of times to run each test case (int).
   * - ``timeout``
     - no
     - Per-test timeout in seconds (int).
   * - ``timeout_session``
     - no
     - Whole-session timeout in seconds (int).
   * - ``modules``
     - no
     - Restrict execution to named modules (comma or space separated).

Execution Pipeline
==================

NTFC processes a manifest in three phases:

Phase 1: Build
---------------

All session configurations are built before any tests start.  Identical
builds (same defconfig, ``build_env``, and ``kv``) are automatically
deduplicated so each unique configuration is built only once.  If any build
fails the entire run is aborted immediately.

Phase 2: Test
-------------

After all builds succeed, a single timestamped result directory is created
(e.g. ``result/2026-04-14_18-30-00/``).  Each session writes its results
into a sub-directory named after the session
(``result/<timestamp>/<session-name>/``).

In **sequential mode** (default) sessions run in manifest order.  With
``fail_fast: true`` execution stops at the first failure.

In **parallel mode** sessions are dispatched to a thread pool.  Resource
tags control concurrency:

* Sessions with **no resources** run fully in parallel.
* Sessions that share at least one resource tag are serialized -- only one
  session holding a given resource can run at a time.
* Resource locks are acquired in a consistent order (sorted by ``id``) to
  prevent deadlocks.

Phase 3: Report
---------------

Individual session JUnit XML reports are merged into a single
``report.xml`` in the shared result directory.  Testsuite names and
testcase classnames are prefixed with the session name
(``<session>::<original>``), so results from different sessions never
collide.

A unified HTML summary is generated from the merged report.

The final directory layout looks like this::

  result/<timestamp>/
      report.xml                           # merged JUnit XML
      report/
          result_summary.txt               # aggregated summary
          result_summary.html
      session-a/
          report.xml                       # session-a JUnit XML
          report.html
          session.config.txt
          ...
      session-b/
          report.xml
          report.html
          session.config.txt
          ...

Resource Tags
=============

Resource tags are arbitrary strings that name shared host resources.  NTFC
does not interpret the tags -- they are purely scheduling hints.

Common examples:

* ``vcan0`` -- virtual CAN interface
* ``pty-bridge`` -- pseudo-terminal bridge
* ``tap0`` -- TAP network interface

Assign the same tag to sessions that would conflict if run simultaneously:

.. code-block:: yaml

   sessions:
     - name: can-tests
       confpath: configs/can.yaml
       testpath: tests/can
       resources: [vcan0]
     - name: gateway-tests
       confpath: configs/gateway.yaml
       testpath: tests/gateway
       resources: [vcan0]
     - name: shell-tests
       confpath: configs/shell.yaml
       testpath: tests/shell
       # no resources -- runs in parallel with anything

With ``parallel: true``, ``can-tests`` and ``gateway-tests`` run one at a
time (both need ``vcan0``), while ``shell-tests`` runs concurrently with
either of them.

Build Deduplication
===================

When multiple sessions share the same defconfig and build environment, NTFC
builds the firmware once and reuses it.  The deduplication key is computed
from:

* Each core's ``defconfig`` path
* Global ``build_env`` key-value pairs
* Global ``kv`` overrides

Sessions that differ only in test-time settings (``testpath``, ``loops``,
``timeout``) share the same build artifact.
