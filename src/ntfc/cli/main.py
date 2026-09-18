############################################################################
# SPDX-License-Identifier: Apache-2.0
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.  The
# ASF licenses this file to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance with the
# License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
# License for the specific language governing permissions and limitations
# under the License.
#
############################################################################

"""Module containing the CLI logic for NTFC."""

import json
import os
import pprint
import sys
from collections.abc import Mapping
from typing import Any, Dict, List, Tuple

import click
import yaml  # type: ignore
from prettytable import PrettyTable

from ntfc.builder import BuilderConfigError, NuttXBuilder
from ntfc.cli.environment import Environment, pass_environment
from ntfc.log.logger import logger
from ntfc.multi import ManifestConfig, MultiSessionRunner
from ntfc.plugins_loader import commands_list
from ntfc.pytest.formatters import list_modules_run, list_tests_run
from ntfc.pytest.mypytest import MyPytest

###############################################################################
# Function: main
###############################################################################


@click.group()
@click.option(
    "--debug/--no-debug",
    default=False,
    is_flag=True,
)
@click.option(
    "--verbose/--no-verbose",
    default=False,
    is_flag=True,
)
@pass_environment
def main(ctx: Environment, debug: bool, verbose: bool) -> bool:
    """VFTC - NuttX Testing Framework for Community."""
    print("-" * 80)
    print(f"NTFC PID: {os.getpid()}", file=sys.stderr)
    print("-" * 80)
    ctx.debug = debug
    ctx.verbose = verbose

    if debug:  # pragma: no cover
        logger.setLevel("DEBUG")
    else:
        logger.setLevel("INFO")

    # handle work after all commands are parsed
    click.get_current_context().call_on_close(cli_on_close)

    # check if --help was called
    if "--help" in sys.argv[1:]:  # pragma: no cover
        ctx.helpnow = True

    return True


def print_yaml_config(config: Dict[str, Any]) -> None:
    """Print YAML configuration."""
    print("YAML config:")
    pp = pprint.PrettyPrinter()
    pp.pprint(config)


def print_json_config(config: Dict[str, Any]) -> None:
    """Print JSON configuration."""
    print("JSON config:")
    pp = pprint.PrettyPrinter()
    pp.pprint(config)


def collect_print_skipped(items: List[Tuple[Any, str]]) -> None:
    """Print skipped tests and reason."""
    if items:
        print("Skipped tests:")
    for item in items:
        print(f"{item[0].location[0]}:{item[0].location[2]}: \n => {item[1]}")


def collect_run(pt: "MyPytest", ctx: Any) -> None:
    """Collect tests."""
    assert ctx.testpath is not None
    col = pt.collect(ctx.testpath)

    print("\nCollect summary:")
    print(
        f"  all: {len(col.allitems)}"
        f"  filtered: {len(col.items)}"
        f"  skipped: {len(col.skipped)}"
    )

    if ctx.collect == "silent":
        return

    # Handle --list-modules option or collect modules
    if ctx.list_modules or ctx.collect in ("modules", "all"):
        list_modules_run(col)

    # Handle --list-tests or -l option
    if ctx.list_tests or ctx.collect in ("collected", "all"):
        list_tests_run(col)

    if ctx.collect in ("skipped", "all"):
        # print skipped test cases
        collect_print_skipped(col.skipped)


def tests_run(pt: "MyPytest", ctx: Any) -> Any:
    """Select and run individual tests by index."""
    assert ctx.testpath is not None

    # First collect to get test list
    col = pt.collect(ctx.testpath)

    if ctx.select_individual_tests:
        # Validate indexes
        invalid_indexes = [
            i
            for i in ctx.select_individual_tests
            if i < 1 or i > len(col.items)
        ]
        if invalid_indexes:
            logger.error(f"❌ Invalid test indexes: {invalid_indexes}")
            logger.error(f"❌ Valid range: 1-{len(col.items)}")
            return -1

        # Get selected tests
        selected_tests = [
            col.items[i - 1] for i in ctx.select_individual_tests
        ]
        test_range = ctx.select_individual_tests
    else:
        # Get all tests
        selected_tests = col.items
        test_range = range(1, len(col.items) + 1)

    # Display selected tests
    print("\n" + "=" * 100)
    print(f"  🚀 RUNNING {len(selected_tests)} SELECTED TEST(S)")
    if ctx.loops > 1:
        print(f"  🔄 Loops: {ctx.loops}")
    print("=" * 100)

    # Create table for selected tests

    table = PrettyTable()
    table.field_names = ["Idx", "Module", "Test Case"]
    table.align["Idx"] = "r"
    table.align["Module"] = "l"
    table.align["Test Case"] = "l"
    table.max_width["Module"] = 40
    table.max_width["Test Case"] = 50

    # Custom border style
    table.horizontal_char = "─"
    table.vertical_char = "│"
    table.junction_char = "┼"

    for idx, test in zip(test_range, selected_tests):
        table.add_row([idx, test.module2, test.name])

    print(table)
    print("=" * 100 + "\n")

    # Convert selected tests to pytest node IDs
    selected_nodeids = [item.nodeid_abs for item in selected_tests]

    # Update test collection to only run selected tests
    return pt.runner(
        ctx.testpath,
        ctx.result,
        ctx.nologs,
        selected_tests=selected_nodeids,
        reinit=False,
    )


def update_nested_dict(
    dict1: Dict[str, Any], dict2: Mapping[str, Any]
) -> Dict[str, Any]:
    """Recursively update nested dictionary.

    Args:
        dict1: Base dictionary to be updated
        dict2: Dictionary to overlay on top of dict1

    Returns:
        Updated dictionary with dict2 merged into dict1
    """
    for k, v in dict2.items():
        if isinstance(v, Mapping):
            dict1[k] = update_nested_dict(dict1.get(k, {}), v)
        else:
            dict1[k] = v
    return dict1


def _find_yaml_files(confpath: str) -> List[str]:
    """Find all YAML files under a directory in deterministic order."""
    yaml_files = []
    for root, _dirs, files in os.walk(confpath):
        for file in files:
            if file.endswith((".yaml", ".yml")):
                yaml_files.append(os.path.join(root, file))
    yaml_files.sort()
    return yaml_files


def _load_yaml_from_directory(confpath: str) -> Dict[str, Any]:
    """Load and merge YAML files from a directory."""
    logger.info(f"Loading YAML config directory: {confpath}")

    conf: Dict[str, Any] = {}
    yaml_files = _find_yaml_files(confpath)
    logger.info(f"Found {len(yaml_files)} YAML files in directory")

    for yaml_file in yaml_files:
        logger.info(f"  Loading: {yaml_file}")
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                file_conf = yaml.safe_load(f)
                conf = update_nested_dict(conf, file_conf)
        except Exception as e:
            logger.warning(f"  Skipping invalid YAML file: {yaml_file} ({e})")

    if not conf:
        raise IOError(f"No valid configuration found in directory: {confpath}")

    return conf


def _load_yaml_from_file(confpath: str) -> Dict[str, Any]:
    """Load YAML configuration from a single file."""
    logger.info(f"Loading YAML config file: {confpath}")
    with open(confpath, "r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    return loaded if isinstance(loaded, dict) else {}


def _load_json_config(jsonconf: str) -> Dict[str, Any]:
    """Load optional JSON session config."""
    logger.info(f"Module config file {jsonconf}")
    with open(jsonconf, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    return loaded if isinstance(loaded, dict) else {}


def _apply_json_args(
    conf: Dict[str, Any], conf_json: Dict[str, Any]
) -> Dict[str, Any]:
    """Apply ``args`` mapping from JSON config into YAML ``config``."""
    json_args = conf_json.get("args", {})
    if isinstance(json_args, Mapping):
        conf["config"] = update_nested_dict(conf.get("config", {}), json_args)
    return conf


def _build_if_needed(ctx: Environment, conf: Dict[str, Any]) -> Dict[str, Any]:
    """Run optional auto-build/flash flow and return updated config."""
    builder = NuttXBuilder(conf, ctx.rebuild)
    if builder.need_build():
        builder.build_all()
        if ctx.flash:
            builder.flash_all()
        conf = builder.new_conf()
    return conf


def load_config_files(
    ctx: Environment,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Load configuration from config files.

    If confpath is a directory, load all YAML files in that directory
    and merge them. If it's a file, load that single file.
    """
    assert ctx.confpath is not None

    if os.path.isdir(ctx.confpath):
        conf = _load_yaml_from_directory(ctx.confpath)
    else:
        conf = _load_yaml_from_file(ctx.confpath)

    conf["config"]["loops"] = ctx.loops

    conf_json: Dict[str, Any] = {}
    if ctx.jsonconf:  # pragma: no cover
        conf_json = _load_json_config(ctx.jsonconf)

    conf = _apply_json_args(conf, conf_json)

    print_yaml_config(conf)
    print_json_config(conf_json)

    conf = _build_if_needed(ctx, conf)

    return conf, conf_json


def multi_run(ctx: Environment) -> int:
    """Run multi-session pipeline from manifest.

    :param ctx: CLI environment with manifest path.
    :return: Exit code (0 = success).
    """
    assert ctx.manifest is not None
    manifest = ManifestConfig.load(ctx.manifest)
    logcfg = ctx.result.get("logcfg") if ctx.result else None
    runner = MultiSessionRunner(
        manifest,
        rebuild=ctx.rebuild,
        verbose=ctx.verbose,
        debug=ctx.debug,
        logcfg=logcfg,
    )
    return runner.run()


def _fuzz_check_tree(cwd: Any, where: str) -> bool:  # pragma: no cover
    """Verify a tree dir contains nuttx/ and apps/; print guidance if not."""
    from pathlib import Path

    cwd = Path(cwd)
    if (cwd / "nuttx").is_dir() and (cwd / "apps").is_dir():
        return True
    print(
        f"[fuzz] ERROR: {where} '{cwd}' must contain both nuttx/ and apps/ "
        f"checkouts (nuttx/ present: {(cwd / 'nuttx').is_dir()}, apps/ "
        f"present: {(cwd / 'apps').is_dir()}). Nothing was built."
    )
    return False


def fuzz_run(ctx: Environment) -> int:  # pragma: no cover  # noqa: C901
    """Run a fuzz config and write its report into a session directory.

    ``build`` / ``mem`` need only the fuzz config (it names board + tree).
    ``ostest`` also needs an NTFC target config via ``--confpath``.
    """
    from pathlib import Path

    from ntfc.fuzz import dataload, discover
    from ntfc.fuzz.campaign import (
        CampaignError,
        board_config_of,
        load_fuzz_config,
    )
    from ntfc.fuzz.engine import (
        _label,
        _surface_names,
        plan_candidates,
        run_campaign,
    )
    from ntfc.log.manager import LogManager

    assert ctx.fuzzpath is not None
    try:
        fuzz = load_fuzz_config(ctx.fuzzpath)
    except CampaignError as exc:
        print(f"[fuzz] ERROR: {exc}")
        return 2

    # The ostest candidate matrix comes from the fuzz config alone, so a
    # --dry-run does not need the target config.
    target = None
    cwd = None
    board = "(target from --confpath)"
    nuttx_root = Path(".")
    if fuzz.needs_target:
        if ctx.fuzz_confpath:
            with open(ctx.fuzz_confpath, "r", encoding="utf-8") as f:
                target = yaml.safe_load(f)
            cwd = Path(target["config"]["cwd"]).resolve()
            target["config"]["cwd"] = str(cwd)
            board = board_config_of(target)
            nuttx_root = cwd / "nuttx"
        elif not ctx.fuzz_dry_run:
            print(
                "[fuzz] ERROR: the 'ostest' feature needs a target config: "
                "pass --confpath <ntfc-config.yaml> (device/board)."
            )
            return 2
    else:
        cwd = Path(str(fuzz.tree)).resolve()
        fuzz.tree = str(cwd)
        fuzz.build_dir = str(Path(fuzz.build_dir).resolve())
        board = str(fuzz.board)
        nuttx_root = cwd / "nuttx"

    if cwd is not None and not _fuzz_check_tree(cwd, "the tree"):
        return 2

    if ctx.fuzz_list:
        profile = dataload.get_profile(fuzz.arch)
        names = _surface_names(
            fuzz, nuttx_root, profile, board, discover.discover
        )
        print(f"fuzz surface for {board}:")
        for n in names:
            print(f"  {n}")
        return 0

    if ctx.fuzz_dry_run:
        subsets = plan_candidates(fuzz, target)
        print(
            f"[fuzz] planned {fuzz.feature} candidates for {board}: "
            f"{len(subsets)}"
        )
        for s in subsets:
            print(f"  {_label(s)}")
        return 0

    def _progress(msg: str) -> None:
        print(msg, flush=True)

    print(
        f"[fuzz] starting {fuzz.feature} campaign on {board} ...", flush=True
    )
    report = run_campaign(fuzz, target, progress=_progress)

    log_manager = LogManager(ctx.result.get("logcfg") if ctx.result else None)
    log_manager.cleanup()
    session_dir = log_manager.new_session_dir()
    report.write(session_dir)

    print(report.text())
    print(f"\n[fuzz] report written to {session_dir}")
    return 1 if report.failed() else 0


@pass_environment
def cli_on_close(ctx: Environment) -> bool:  # noqa: C901
    """Handle all work on Click close."""
    if ctx.helpnow:  # pragma: no cover
        # do nothing if help was called
        return True

    # multi-session mode
    if ctx.runmulti:
        ret = multi_run(ctx)
        if ret != 0:
            exit(1)
        return True

    # fuzzing mode
    if ctx.runfuzz:
        ret = fuzz_run(ctx)
        if ret != 0:
            exit(1)
        return True

    # load configuration
    try:
        conf, conf_json = load_config_files(ctx)
    except BuilderConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    # exit now when build only mode
    if ctx.runbuild:
        return True

    pt = MyPytest(conf, ctx.exitonfail, ctx.verbose, conf_json, ctx.modules)

    if ctx.runcollect:
        collect_run(pt, ctx)

    if ctx.runtest:
        ret = tests_run(pt, ctx)
        if ret != 0:
            exit(1)

    return True


###############################################################################
# Function: click_final_init
###############################################################################


def click_final_init() -> None:
    """Handle final Click initialization."""
    # add interfaces
    for cmd in commands_list:
        main.add_command(cmd)


# final click initialization
click_final_init()
