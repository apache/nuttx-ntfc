=====
Usage
=====

Commands
========

You can run NTFC as a Python module:

.. code-block:: bash

   python -m ntfc [OPTIONS] COMMAND [ARGS]...

For commands details use ``--help`` option.

``collect`` command
-------------------

Collect-only test cases.

.. code-block:: bash

   python -m ntfc collect [OPTIONS] [COLLECT]


The ``COLLECT`` argument specify what data to print:

* ``collected`` - print collected items only.

* ``skipped`` - print skipped items only.

* ``all``-  (DEFAULT) print all possible data.

* ``silent`` - don't print any additional data.

Options:

* ``--testpath PATH`` - Path to test cases.
  Can be also set with environment variable ``NTFC_TESTPATH``.
  Default: ``./external/nuttx-testing``.

  With this option you can also narrow down the tests
  to run by specifying the path to the test sub-module,
  example: ``--testpath ./external/nuttx-testing/arch/nsh``

* ``--confpath PATH`` - Path to test configuration file.
  Can be also set with environmentvariable ``NTFC_CONFPATH``.
  Default: ``./external/config.yaml``

* ``--rebuild`` - Always rebuild configuration. Default: True.

``test`` command
----------------

Run test cases.

.. code-block:: bash

   python -m ntfc test [OPTIONS]

Test Filtering Options:

* ``-c, --modules TEXT`` - Execute specific test module(s).
  Use quotes for multiple modules: ``-c "module1 module2"`` or
  comma-separated: ``-c module1,module2``.
  Example: ``-c "Nuttx_System_Arch_Nsh Nuttx_System_Arch_Example"``

  This option overrides the configuration from the JSON session config.

* ``-i, --index INTEGER`` - Select and execute individual tests by index.
  Use with ``-l`` to see available indexes. Can be specified multiple times.
  Example: ``-i 1 -i 5 -i 10``

* ``--loops INTEGER`` - Number of times to run each test case.
  Default: 1.
  Example: ``--loops 3`` will run each test 3 times.

  This option overrides the configuration from the YAML config.

* ``--collect-only`` - Collect tests without executing them.
  Useful for verifying test collection and filtering.

  Equivalent to using ``python -m ntfc collect silent``.

* ``-l, --list-tests`` - List all available test cases with their indexes.
  Displays test index, name, file location, and line number in a
  formatted table.
  Use with ``-c`` to filter by module.

  Equivalent to using ``python -m ntfc collect collected``.

* ``--list-modules`` - List all available test modules.
  Displays module name, number of tests, and directory in a formatted table.

  Equivalent to using ``python -m ntfc collect modules``.

Log Management Options:

* ``--logcfg PATH`` - Path to log configuration file.
  Default: built-in ``log.yaml`` shipped with the ntfc package.
  When a custom file is absent all cleanup rules are disabled and
  results are stored in ``./result``.

* ``--nologs`` - When set, test logs are not saved locally and log
  management is skipped entirely.

Test Execution Options:

* ``--testpath PATH`` - Path to test cases.
  Can be also set with environment variable ``NTFC_TESTPATH``.
  Default: ``./external/nuttx-testing``

* ``--confpath PATH`` - Path to test configuration file.
  Can be also set with environmentvariable ``NTFC_CONFPATH``.
  Default: ``./external/config.yaml``
  For details look at ``Documentation/config.yaml``.

* ``--jsonconf PATH`` - Path to test session configuration file.
  Default: None.
  For details look at ``Documentation/session.json``.

Log Notes:

* Collected logs are stored per test under
  ``result/<timestamp>/<product>/<core>/``.
  ``*.console.txt`` holds the raw console output.
* ``*.device.txt`` captures device control/status events and includes
  console input lines tagged as ``console_in`` to correlate commands with
  events.
  Device events that happen before log collection starts are buffered and
  written when the device log file is opened.

* ``--exitonfail / --no-exitonfail`` - Stop test execution on first failure.
  Default: False (continue on failure).

* ``--rebuild`` - Always rebuild configuration. Default: True.

* ``--flash`` - Flash image. Default: False.

``build`` command
~~~~~~~~~~~~~~~~~

Build NuttX test image from YAML configuration and try to flash.
This functionality is managed by the :class:`ntfc.builder.NuttXBuilder` class.
The build command always rebuilds the configuration and by default attempts to
flash the resulting image to the DUT.

.. code-block:: bash

   python -m ntfc build [OPTIONS]

Options:

* ``--confpath PATH`` - Path to test configuration file.
  Can be also set with environmentvariable ``NTFC_CONFPATH``.
  Default: ``./external/config.yaml``

* ``--flash / --no-flash``  Flash image. Default: True.

Log Management
==============

NTFC reads log configuration from the built-in ``log.yaml`` bundled
with the ntfc package (override with ``--logcfg``).  The file controls
where test sessions are stored and runs automatic cleanup before each
session.

Example ``log.yaml``:

.. code-block:: yaml

   log:
     # Directory where test result sessions are stored
     results_dir: "./result"

     # Remove session directories older than this many days (null to disable)
     max_age_days: 30

     # Keep only this many of the latest session directories (null to disable)
     max_count: 100

     # Remove oldest session directories when total size exceeds this value
     # in megabytes (null to disable)
     max_size_mb: 50

Session directories are named with the timestamp format
``YYYY-MM-DD_HH-MM-SS`` (e.g. ``2025-03-01_14-30-00``).  This format is
managed centrally by ``LogManager`` so the name is consistent regardless of
how the session is created.

Cleanup rules are applied simultaneously before a new session directory is
created.  All three rules are evaluated independently and the union of their
results is removed:

* ``max_age_days`` — removes sessions whose last-modified timestamp is older
  than the configured number of days.

* ``max_count`` — removes the oldest sessions so that at most the configured
  number of sessions remain.

* ``max_size_mb`` — removes the oldest sessions until the total size of the
  results directory falls within the configured limit.

Heartbeat Monitoring
====================

Periodically sends ``echo '[heartbeat ...]'`` to detect devices stuck in a
busy-loop (flooding output but not responding to commands).  On ``threshold``
consecutive failures the device is marked ``BUSY_LOOP``.

.. code-block:: yaml

   config:
     heartbeat:
       enabled: True
       interval: 60    # seconds between probes, minimum 30
       threshold: 3    # consecutive failures to declare busyloop

Device Recovery
===============

Reboots the device when it enters an unhealthy state (crash or busy-loop).
Remaining tests are skipped if all retries fail.

.. code-block:: yaml

   config:
     recovery:
       max_retries: 3      # reboot attempts before skipping remaining tests
       base_delay: 2.0     # seconds between retries (doubles each attempt)

Signal Handlers
===============

During a test run, NTFC installs custom signal handlers to aid debugging.
This behavior is implemented in the
:class:`ntfc.pytest.signal_plugin.SignalPlugin`.
Send a signal to the NTFC process (use the PID printed at startup) with
``kill -<SIGNAL> <PID>``.

* ``SIGUSR1`` — Runs the ``ps`` command on the device under test and prints
  the output to stdout.

* ``SIGUSR2`` — Try to force panic the device.

* ``SIGQUIT`` — Dumps comprehensive NTFC debug information to stderr.

The handlers are installed at pytest session start and restored when the
session finishes.
