=========================================
Test Session Configuration (session.json)
=========================================

This file allows you to fine-tune test execution: module inclusion/exclusion
and argument overrides. Path to test session configuration file is passed with
``--jsonconf PATH`` option.

**Structure:**

.. code-block:: json

   {
     "module": {
       "include_module": [
         "Nuttx_System_Arch_Os_Integration",
         "Nuttx_System_Tools"
       ],
       "exclude_module": [
         "Nuttx_System_Arch_Os_Performance"
       ],
       "exclude_test": [
         "test_ltp_integration[ltp_interfaces_pthread_rwlock_unlock_4_2]"
       ],
       "order": []
     },
     "args": {
       "timeout": 600,
       "timeout_session": 7200,
       "loops": 3,
       "custom_option": "value",
       "kv": {}
     }
   }

**Fields:**

- ``include_module``: Modules to include (empty = include all)

- ``exclude_module``: Modules to exclude

- ``exclude_test``: Individual tests to exclude, by pytest item name. For a
  parametrized test the name includes the parameter, e.g.
  ``test_ltp_integration[ltp_interfaces_pthread_rwlock_unlock_4_2]``. A name
  matches in every module, so a board can blacklist a single case that is
  known to fail on it without touching the test suite. An excluded test is
  dropped from the session the same way as the tests of an excluded module.

- ``order``: Force execution order. Specifies a list of objects with ``module``
  and ``value``.

  Tests are grouped by their order value:

  - Positive values (e.g., "1", "2"): Placed at the beginning of the test
    session. Lower values come first.

  - Unspecified: Placed in the middle.

  - Negative values (e.g., "-1", "-2"): Placed at the end. Higher absolute
    values come last (e.g., -1 comes before -2).

  - Multiple modules with the same order value follow their original
    discovery (FIFO) order.

- ``args``: Optional configuration overrides for the YAML ``config`` section.
  Keys in ``args`` override existing YAML values. New keys are added if they
  do not exist in YAML.

  Example: ``"args": {"timeout": 600}`` overrides ``config.timeout`` from
  ``config.yaml``.

- ``args.kv``: Optional Kconfig overrides for the global ``config.kv`` layer
  from ``config.yaml`` for the current session. Uses the same mapping syntax
  as YAML ``config.kv``. Per-core ``kv`` in YAML still has higher priority.

Module Name Generation
======================

Module names in ``session.json`` combine base module name from ``ntfc.yaml``
with test case directory path.

**Rule:**

1. Start with ``module`` field from ``ntfc.yaml``
2. Append directory path but replace ``/`` with ``_``
3. Capitalize first letter of each directory

**Examples:**

- Base: ``Nuttx_System``, Path: ``arch/os/integration/`` ->
  ``Nuttx_System_Arch_Os_Integration``
- Base: ``CUSTOM``, Path: ``dir1/dir2/dir3/`` -> ``CUSTOM_Dir1_Dir2_Dir3``

**Usage:**

Include specific modules:

.. code-block:: json

   {
     "module": {
       "include_module": [
         "Nuttx_System_Arch_Os_Integration",
         "Nuttx_System_Tools_Gdb"
       ],
       "exclude_module": []
     }
   }

Exclude specific modules:

.. code-block:: json

   {
     "module": {
       "include_module": [],
       "exclude_module": [
         "Nuttx_System_Arch_Os_Performance"
       ]
     }
   }

Override YAML config options for one test session:

.. code-block:: json

   {
     "module": {
       "include_module": [],
       "exclude_module": [],
       "order": []
     },
     "args": {
       "timeout": 600,
       "timeout_session": 7200,
       "loops": 3,
       "kv": {
         "CONFIG_DEBUG_FEATURES": "y",
         "CONFIG_IDLETHREAD_STACKSIZE": "4096"
       }
     }
   }

This overrides values from ``config.yaml`` ``config`` section (for example
``config.timeout``) only for the current session.
