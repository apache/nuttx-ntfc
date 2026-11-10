=============
API Reference
=============

This page provides an overview of the NTFC internal API.

Core Modules
============

.. autosummary::
   :toctree: _autosummary
   :recursive:

   ntfc.builder
   ntfc.core
   ntfc.coreconfig
   ntfc.cores
   ntfc.envconfig
   ntfc.log.logger
   ntfc.parallel
   ntfc.plugins_loader
   ntfc.product
   ntfc.productconfig
   ntfc.products
   ntfc.log.report
   ntfc.testfilter

Device Interface
================

.. autosummary::
   :toctree: _autosummary
   :recursive:

   ntfc.device.common
   ntfc.device.host
   ntfc.device.netconsole
   ntfc.device.netdev
   ntfc.device.nuttx
   ntfc.device.qemu
   ntfc.device.renode
   ntfc.device.serial
   ntfc.device.sim

Pytest Integration
==================

.. autosummary::
   :toctree: _autosummary
   :recursive:

   ntfc.pytest.collected
   ntfc.pytest.collecteditem
   ntfc.pytest.collector
   ntfc.pytest.configure
   ntfc.pytest.formatters
   ntfc.pytest.mypytest
   ntfc.pytest.runner
   ntfc.pytest.signal_plugin
