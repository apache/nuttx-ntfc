==================
Writing Test Cases
==================

NTFC supports comprehensive test case development with flexible test discovery
and execution. Test cases are organized in modules with YAML configuration files
defining requirements and metadata.

Test Module Structure
=====================

Each test module directory contains:

.. code-block:: text

   test-module/
   ├── ntfc.yaml              # Module configuration (required)
   ├── conftest.py            # Pytest configuration (optional)
   ├── test_*.py              # Test case files
   ├── subdir/
   │   └── test_*.py          # Nested test cases
   └── ...

Each test function in a module must have a unique name!

Module Configuration (ntfc.yaml)
=================================

Located in the root of each test module directory.

**Structure:**

.. code-block:: yaml

   module: "Nuttx_System"              # Module identifier

   dependencies:                       # Optional: Python dependencies
     - toml

   requirements:                       # NuttX configuration requirements
     - ["CONFIG_DEBUG_SYMBOLS", True]
     - ["CONFIG_SYSTEM_NSH", True]
     - ["CONFIG_INIT_ENTRYPOINT", "nsh_main"]

Fields:

- ``module``: Unique module identifier. Hierarchical names use underscores
  (e.g., ``Nuttx_System``)
- ``dependencies``: List of Python packages required by test cases
- ``requirements``: NuttX configuration requirements. Tests skip if not met.

Configuration Requirements
===========================

Requirements are specified as ``[config_key, expected_value]`` pairs.

Boolean Requirements:

.. code-block:: yaml

   requirements:
     - ["CONFIG_DEBUG_SYMBOLS", True]          # CONFIG must be enabled
     - ["CONFIG_DEBUG_FEATURES", False]        # CONFIG must be disabled

String/Value Requirements:

.. code-block:: yaml

   requirements:
     - ["CONFIG_INIT_ENTRYPOINT", "nsh_main"]  # CONFIG must equal value
     - ["CONFIG_TASK_NAME_SIZE", "32"]         # CONFIG must equal value

Wildcard Requirements:

.. code-block:: yaml

   requirements:
     - ["CONFIG_INIT_FILEPATH", "*"]           # CONFIG must be set (any value)

Alternative Requirements (any one entry satisfies the requirement):

.. code-block:: yaml

   requirements:
     - [["CONFIG_INIT_ENTRYPOINT", "nsh_main"], ["CONFIG_INIT_FILEPATH", "*"]]

How Requirements Work:

1. NTFC reads NuttX ``.config`` file from configuration
2. Extracts configuration values via :class:`ntfc.coreconfig.CoreConfig`
3. Compares against requirements
4. Raise assertion if any requirement not met

Example:

Module requires NSH (NuttX Shell) as entry point:

.. code-block:: yaml

   module: "Nuttx_System_Syscall"

   requirements:
     - ["CONFIG_DEBUG_SYMBOLS", True]
     - ["CONFIG_SYSTEM_NSH", True]
     - ["CONFIG_INIT_ENTRYPOINT", "nsh_main"]

If ``.config`` doesn't have all these settings, assertion is raised.

Test Case Organization
======================

Organize test cases by functionality in subdirectories:

.. code-block:: text

   nuttx-testing/
   ├── ntfc.yaml
   ├── arch/
   │   ├── test_pthread.py
   │   └── os/
   │       ├── test_task.py
   │       └── integration/
   │           └── test_syscall.py
   ├── fs/
   │   ├── test_vfs.py
   │   └── test_mount.py
   └── libc/
       └── test_stdio.py

Directory paths determine module hierarchy. For example:

- ``ntfc.yaml`` module: ``Nuttx_System``
- ``arch/test_pthread.py`` -> ``Nuttx_System_Arch``
- ``arch/os/integration/test_syscall.py`` ->
  ``Nuttx_System_Arch_Os_Integration``

Use this for filtering tests via ``session.json``.

Pytest Configuration (conftest.py)
==================================

``conftest.py`` enables advanced test generation, filtering, and configuration
for test modules. It can use pytest hooks to dynamically generate test cases and
modify test collection.

Common Uses:

1. Dynamic test generation from ELF symbols (e.g., LTP tests)
2. Test case filtering based on blacklists, skip lists, crash lists
3. Custom timeout management for specific tests
4. Test parameter management (expected outputs, test variations)
5. Setup/teardown logic using fixtures

Key Pytest Hooks:

.. list-table::
   :header-rows: 1

   * - Hook
     - Purpose
     - Called
   * - ``pytest_generate_tests``
     - Generate parametrized test cases
     - During test collection
   * - ``pytest_collection_modifyitems``
     - Modify collected test items
     - After test collection
   * - ``@pytest.fixture``
     - Define reusable test setup/teardown
     - Before/after tests

Test Case Patterns
===================

NTFC supports multiple test case patterns.

Simple Command Test
--------------------

Execute NSH command and verify output:

.. code-block:: python

   import pytest

   @pytest.mark.cmd_check("test_main")
   def test_simple():
       cmd = "test"
       expected = ["TEST PASSED"]
       ret = pytest.product.sendCommand(cmd, expected, timeout=15)
       assert ret == 0

Decorators:

- ``@pytest.mark.cmd_check("symbol_name")``: Verify ELF symbol exists
- ``@pytest.mark.dep_config("CONFIG_X", "CONFIG_Y")``: Skip if configs not
  enabled

The :meth:`~ntfc.products.ProductsHandler.sendCommand` method handles
execution and verification.

Parametrized Command Test
--------------------------

Run multiple test variations:

.. code-block:: python

   @pytest.mark.cmd_check("cmocka")
   @pytest.mark.dep_config("CONFIG_TESTS_TESTSUITES", "CONFIG_CM_SYSCALL_TEST")
   @pytest.mark.parametrize("case,expected", [
       ("test1", ["PASSED"]),
       ("test2", ["PASSED"]),
       ("test3", ["OK"])
   ])
   def test_cmocka_cases(case, expected):
       cmd = f"cmocka -t {case}"
       ret = pytest.product.sendCommand(cmd, expected, timeout=300)
       assert ret == 0

Dynamic Test Generation
------------------------

Generate tests from ELF symbols (e.g., LTP tests) using
:class:`~ntfc.lib.elf.elf_parser.ElfParser`:

.. code-block:: python

   import pytest
   from ntfc.lib.elf.elf_parser import ElfParser

   def pytest_generate_tests(metafunc):
       if "ltp_case" in metafunc.fixturenames:
           elf = ElfParser("path/to/nuttx")
           cases = elf.get_symbols("ltp_.*_main")
           metafunc.parametrize("ltp_case", cases)

   def test_ltp(ltp_case):
       ret = pytest.product.sendCommand(ltp_case, [], timeout=60)
       assert ret == 0

Available Fixtures and Marks
=============================

NTFC provides built-in fixtures and pytest marks for test development.

Built-in Fixtures:

TODO

Custom Fixtures:

Define setup/teardown fixtures for test preparation:

.. code-block:: python

   @pytest.fixture(scope="function")
   def setup_device():
       """Setup device state before test."""
       logging.info("Setting up device")
       pytest.product.sendCommand("init_cmd", timeout=2)

       yield  # Test runs here

       # Cleanup
       logging.info("Cleaning up device")
       pytest.product.sendCommand("cleanup_cmd", timeout=2)

   def test_with_setup(setup_device):
       ret = pytest.product.sendCommand("test", ["PASS"], timeout=15)
       assert ret == 0

Available Marks:

.. list-table::
   :header-rows: 1

   * - Mark
     - Purpose
     - Example
   * - ``@pytest.mark.cmd_check()``
     - Verify ELF symbol exists before running test
     - ``@pytest.mark.cmd_check("test_main")``
   * - ``@pytest.mark.dep_config()``
     - Skip test if config options not enabled
     - ``@pytest.mark.dep_config("CONFIG_X", "CONFIG_Y")``
   * - ``@pytest.mark.parametrize()``
     - Run test with multiple parameter sets
     - ``@pytest.mark.parametrize("param", [val1, val2])``
   * - ``@pytest.mark.repeat()``
     - Repeat test multiple times
     - ``@pytest.mark.repeat(5)``
   * - ``@pytest.mark.run()``
     - Mark specific tests for execution
     - ``@pytest.mark.run()``
   * - ``@pytest.mark.skip()``
     - Skip test conditionally
     - ``@pytest.mark.skip(reason="not ready")``
   * - ``@pytest.mark.parser_binary()``
     - Discover and run test framework tests (cmocka / custom) as pytest items
     - ``@pytest.mark.parser_binary("bin", list_pattern=..., result_pattern=...)``

Example - Test Repetition:

.. code-block:: python

   @pytest.mark.repeat(3)
   def test_stability():
       """Run this test 3 times to check stability."""
       ret = pytest.product.sendCommand("test", ["PASS"], timeout=15)
       assert ret == 0

Test Framework Parsers
======================

.. toctree::
   :hidden:

   parsers

NTFC provides built-in parsers for test frameworks (cmocka, gtest, custom).
See :doc:`parsers` for the full reference.

Interaction with Products and Cores
===================================

NTFC provides several ways to interact with the devices under test (DUTs).
Depending on the test scenario, you might want to send commands to all devices
simultaneously, a specific device, or a specific CPU core within a device.

Hierarchy Overview
------------------

- ``pytest.products``: A list containing all configured
  :class:`ntfc.product.Product` instances.
- ``pytest.product``: A global handler (:class:`ntfc.products.ProductsHandler`)
  that acts as a proxy to all products.
- :class:`ntfc.product.Product`: Represents a physical or virtual device,
  which contains one or more cores.
- :class:`ntfc.core.ProductCore`: Represents an individual CPU core (e.g., in
  AMP or SMP systems).

Interaction Scopes
------------------

All Products and All Cores
~~~~~~~~~~~~~~~~~~~~~~~~~~

To execute a command on every configured product and every core within those
products simultaneously, use ``pytest.product``. Commands are executed in
parallel across products.

.. code-block:: python

   # Sends 'ls' to all cores of all products in parallel
   ret = pytest.product.sendCommand("ls", ["nsh"])
   assert ret == 0

Consequences: If any product or core fails to meet the expectations, the
return status will indicate failure. This is the most common way to write
generic tests.

All Cores in a Specific Product
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you have multiple products (e.g., a gateway and a sensor) and only want to
interact with one of them, use the ``pytest.products`` list.

.. code-block:: python

   # Interact only with the first product
   product0 = pytest.products[0]
   product0.sendCommand("help")

   # Interact only with the second product
   product1 = pytest.products[1]
   product1.sendCommand("ifconfig")

Specific Core in a Specific Product
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To target a specific CPU core (e.g., the second core of the first product), use
the :meth:`~ntfc.product.Product.core` method.

.. code-block:: python

   # Target Core 1 (second core) of Product 0
   core = pytest.products[0].core(1)
   core.sendCommand("ps")

Consequences: This bypasses the parallel execution logic of the product
handler and communicates directly with the specified core's device interface.

Shortcut for First Product's Core
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

As a convenience for the most common case (one product, specific core),
``pytest.product.core(n)`` proxies to the first product's core.

.. code-block:: python

   # Shortcut for pytest.products[0].core(0)
   pytest.product.core(0).sendCommand("free")

Command Methods
---------------

The following methods are available on ``pytest.product``,
:class:`~ntfc.product.Product` instances, and :class:`~ntfc.core.ProductCore`
instances:

.. list-table::
   :header-rows: 1

   * - Method
     - Description
     - Example
   * - ``sendCommand(cmd, expects, args, timeout, ..., fail_pattern)``
     - Send command and wait for expected response (list or regex). Returns
       ``CmdStatus.FAILED`` if ``fail_pattern`` is found in the output.
     - ``pytest.product.sendCommand("ls", ["root"], timeout=15)``
   * - ``sendCommandReadUntilPattern(cmd, pattern, args, timeout, fail_pattern)``
     - Send command and read until a specific pattern is found. Returns
       ``CmdStatus.FAILED`` if ``fail_pattern`` is found in the output.
     - ``pytest.product.sendCommandReadUntilPattern("hi", "Hi", timeout=15)``
   * - ``readUntilPattern(pattern, timeout, fail_pattern)``
     - Read device output without sending a command. Returns ``CmdStatus.SUCCESS``
       when ``pattern`` is found or ``CmdStatus.FAILED`` when ``fail_pattern``
       is found. Useful for programs already running on the device.
     - ``pytest.product.readUntilPattern("PASS", fail_pattern="FAIL",
       timeout=60)``
   * - ``sendCtrlCmd(ctrl_char)``
     - Send a control character (e.g., ``"c"`` for Ctrl+C).
     - ``pytest.product.sendCtrlCmd("c")``
   * - ``reboot(timeout)``
     - Reboot the target(s).
     - ``pytest.product.reboot()``

Fail Pattern Detection
-----------------------

Both ``sendCommand`` and ``sendCommandReadUntilPattern`` accept an optional
``fail_pattern`` argument. When the pattern is found anywhere in the command
output the call returns ``CmdStatus.FAILED`` (-3), regardless of whether the
success pattern also matched. This lets tests fail explicitly on known error
strings without having to parse the return value manually.

``fail_pattern`` accepts the same types as the corresponding ``expects`` /
``pattern`` argument: a single string (or bytes), or a list of strings/bytes.
For ``sendCommand`` the ``regexp`` flag also applies to ``fail_pattern``.

.. code-block:: python

   import pytest
   from ntfc.device.common import CmdStatus

   def test_no_errors():
       # Fail if "ERROR" or "PANIC" appears anywhere in the output
       ret = pytest.product.sendCommand(
           "run_test",
           ["PASSED"],
           fail_pattern=["ERROR", "PANIC"],
           timeout=30,
       )
       assert ret == CmdStatus.SUCCESS

   def test_no_errors_regex():
       # Fail on regex pattern (e.g. any "err<digits>" string)
       ret = pytest.product.sendCommand(
           "run_test",
           ["PASSED"],
           fail_pattern=r"err\d+",
           regexp=True,
           timeout=30,
       )
       assert ret == CmdStatus.SUCCESS

   def test_read_until_no_crash():
       ret = pytest.product.sendCommandReadUntilPattern(
           "long_cmd",
           "Done",
           fail_pattern=["Assertion failed", "kernel panic"],
           timeout=60,
       )
       assert ret.status == CmdStatus.SUCCESS

Reading Without Sending a Command
-----------------------------------

``readUntilPattern`` reads device output without sending a command first.
It is intended for programs that are already running on the device (e.g.
launched by a previous ``sendCommand``) and whose pass/fail result must be
captured from their standard output.

The method blocks until one of three things happens:

- ``pattern`` is matched → returns ``CmdReturn`` with ``CmdStatus.SUCCESS``
- ``fail_pattern`` is matched → returns ``CmdReturn`` with ``CmdStatus.FAILED``
  (exits immediately, does not wait for ``pattern``)
- Timeout expires → returns ``CmdReturn`` with ``CmdStatus.TIMEOUT``

``pattern`` is required. ``fail_pattern`` accepts a single string/bytes or a
list, treated as regex.

.. code-block:: python

   import pytest
   from ntfc.device.common import CmdStatus

   def test_background_test_runner():
       # Start a long-running test suite (fire and forget)
       pytest.product.sendCommand("run_suite &", timeout=2)

       # Wait for the suite to finish, catching pass/fail output
       ret = pytest.product.readUntilPattern(
           "All tests passed",
           fail_pattern=["FAILED", "Assertion failed", "kernel panic"],
           timeout=120,
       )
       assert ret.status == CmdStatus.SUCCESS

   def test_boot_sequence():
       pytest.product.reboot()
       # Wait for the shell prompt after reboot
       ret = pytest.product.readUntilPattern("nsh>", timeout=30)
       assert ret.status == CmdStatus.SUCCESS
