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

"""Report generation module for NTFC."""

import copy
import glob
import html
import os
import re
from collections import defaultdict
from typing import Any, Dict
from xml.etree import ElementTree

from prettytable import PrettyTable

from ntfc.log.logger import logger


class Reporter:
    """Report generator for NTFC test results."""

    def __init__(self) -> None:
        """Initialize Reporter."""
        self._template_dir = os.path.join(
            os.path.dirname(__file__), "templates"
        )
        self._module_html_template = self._load_template("module_report.html")

    def _load_template(self, template_name: str) -> str:
        """Load HTML template from file.

        :param template_name: Name of the template file
        :return: Template content as string
        """
        template_path = os.path.join(self._template_dir, template_name)
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()

    def _split_xml_by_module(  # noqa: C901
        self, xml_file: str, output_dir: str
    ) -> Dict[str, str]:
        """Split a JUnit XML report into per-module files.

        :param xml_file: Path to the single JUnit XML report
        :param output_dir: Directory to write per-module XML files
        :return: Dictionary mapping module names to their XML file paths
        """
        if not os.path.exists(xml_file):
            return {}

        try:
            tree = ElementTree.parse(xml_file)
            root = tree.getroot()
        except ElementTree.ParseError:  # pragma: no cover
            return {}

        # Group test cases by module
        modules: Dict[str, Any] = defaultdict(
            lambda: {
                "tests": 0,
                "failures": 0,
                "errors": 0,
                "skipped": 0,
                "time": 0.0,
                "testcases": [],
            }
        )

        # Find all testcases and group by module
        for testcase in root.findall(".//testcase"):
            # Extract module name from classname
            classname = testcase.get("classname", "unknown")
            module_name = classname.split("::")[0].replace(".py", "")
            module_name = os.path.basename(module_name)

            modules[module_name]["testcases"].append(testcase)

        # Create per-module XML files
        module_files = {}
        for idx, (module_name, data) in enumerate(sorted(modules.items()), 1):
            testcases = data["testcases"]

            # Calculate statistics
            tests = len(testcases)
            failures = sum(
                1 for tc in testcases if tc.find("failure") is not None
            )
            errors = sum(1 for tc in testcases if tc.find("error") is not None)
            skipped = sum(
                1 for tc in testcases if tc.find("skipped") is not None
            )
            time_total = sum(float(tc.get("time", 0)) for tc in testcases)

            # Create new testsuites/testsuite structure
            new_testsuites = ElementTree.Element("testsuites")
            new_testsuite = ElementTree.SubElement(new_testsuites, "testsuite")
            new_testsuite.set("tests", str(tests))
            new_testsuite.set("failures", str(failures))
            new_testsuite.set("errors", str(errors))
            new_testsuite.set("skipped", str(skipped))
            new_testsuite.set("time", str(time_total))
            new_testsuite.set("name", module_name)

            # Add all test cases, including nested elements such as
            # <properties><property/></properties>
            for testcase in testcases:
                new_testsuite.append(copy.deepcopy(testcase))

            # Write per-module XML file
            output_file = os.path.join(
                output_dir, f"{idx:03d}_{module_name}.xml"
            )
            new_tree = ElementTree.ElementTree(new_testsuites)
            new_tree.write(output_file)
            module_files[module_name] = output_file

        return module_files

    def _generate_html_for_module(  # noqa: C901
        self, xml_file: str, html_file: str
    ) -> None:
        """Generate HTML report for a module from its XML file.

        :param xml_file: Path to the module's JUnit XML file
        :param html_file: Path where to write the HTML report
        """
        tree = ElementTree.parse(xml_file)
        testsuite = tree.getroot().find("testsuite")

        if testsuite is None:  # pragma: no cover
            return

        # Extract module name
        module_name = testsuite.get("name", "Report")

        # Extract statistics
        tests = int(testsuite.get("tests", 0))
        failures = int(testsuite.get("failures", 0))
        errors = int(testsuite.get("errors", 0))
        skipped = int(testsuite.get("skipped", 0))
        passed = tests - failures - errors - skipped
        time_total = float(testsuite.get("time", 0))

        # Collect test cases
        testcases = []
        for testcase in testsuite.findall("testcase"):
            tc_info = {
                "name": testcase.get("name", "Unknown"),
                "classname": testcase.get("classname", ""),
                "time": float(testcase.get("time", 0)),
                "status": "passed",
                "message": "",
            }

            if testcase.find("failure") is not None:  # pragma: no cover
                tc_info["status"] = "failed"
                failure = testcase.find("failure")
                if failure is not None:
                    tc_info["message"] = failure.get("message", "")
            elif testcase.find("error") is not None:  # pragma: no cover
                tc_info["status"] = "error"
                error = testcase.find("error")
                if error is not None:
                    tc_info["message"] = error.get("message", "")
            elif testcase.find("skipped") is not None:  # pragma: no cover
                tc_info["status"] = "skipped"
                skipped_elem = testcase.find("skipped")
                if skipped_elem is not None:
                    tc_info["message"] = skipped_elem.get("message", "")

            testcases.append(tc_info)

        # Generate HTML from template
        html_content = self._render_module_html_template(
            module_name,
            tests,
            passed,
            failures,
            errors,
            skipped,
            time_total,
            testcases,
        )

        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)

    def _render_module_html_template(
        self,
        module_name: str,
        tests: int,
        passed: int,
        failures: int,
        errors: int,
        skipped: int,
        time_total: float,
        testcases: list[Dict[str, Any]],
    ) -> str:
        """Render HTML template for module report.

        :param module_name: Name of the test module
        :param tests: Total number of tests
        :param passed: Number of passed tests
        :param failures: Number of failed tests
        :param errors: Number of error tests
        :param skipped: Number of skipped tests
        :param time_total: Total execution time
        :param testcases: List of test case dictionaries
        :return: HTML string for the report
        """
        # Color codes for status
        colors = {
            "passed": "#28a745",
            "failed": "#dc3545",
            "error": "#ffc107",
            "skipped": "#6c757d",
        }

        # Generate test case rows
        testcase_rows = ""
        for tc in testcases:
            color = colors.get(tc["status"], "#999")
            testcase_rows += f"""        <tr>
          <td>{html.escape(tc['name'])}</td>
          <td style="color: {color}; font-weight: bold;">
            {tc['status'].upper()}
          </td>
          <td>{tc['time']:.3f}s</td>
          <td>{html.escape(tc['message'][:100])}</td>
        </tr>
"""

        # Calculate pass rate
        pass_rate = (passed / tests * 100) if tests > 0 else 0

        # Load and render template
        template = self._module_html_template
        if not template:  # pragma: no cover
            return ""

        # Simple string formatting for template
        html_content = template.replace(
            "{{ module_name }}", html.escape(module_name)
        )
        html_content = html_content.replace("{{ passed }}", str(passed))
        html_content = html_content.replace("{{ failures }}", str(failures))
        html_content = html_content.replace("{{ errors }}", str(errors))
        html_content = html_content.replace("{{ skipped }}", str(skipped))
        html_content = html_content.replace(
            "{{ time_total }}", f"{time_total:.2f}"
        )
        html_content = html_content.replace(
            "{{ pass_rate }}", f"{pass_rate:.1f}"
        )
        html_content = html_content.replace(
            "{{ testcase_rows }}", testcase_rows
        )

        return html_content

    def generate_result_summary(self, session_dir: str) -> None:
        """Generate final result summary.

        This function generates result_summary.txt and result_summary.html
        files, parsing all JUnit XML reports and creating a summary table
        with statistics.

        :param session_dir: Path to the test session directory
                            containing XML reports
        """
        logger.info("[Report] Generating final result summary...")

        report_dir = os.path.join(session_dir, "report")
        os.makedirs(report_dir, exist_ok=True)

        # Check if we need to split report.xml into per-module files
        single_report = os.path.join(session_dir, "report.xml")
        if os.path.exists(single_report):
            logger.info(
                "[Report] Splitting single report into per-module "
                "reports..."
            )
            module_files = self._split_xml_by_module(single_report, report_dir)

            # Generate per-module HTML reports
            for module_name, xml_file in module_files.items():
                html_file = xml_file.replace(".xml", ".html")
                self._generate_html_for_module(xml_file, html_file)
                logger.info(
                    f"[Report] Generated report for module: " f"{module_name}"
                )

            # Remove the original single report files to avoid confusion
            single_html = os.path.join(session_dir, "report.html")
            if os.path.exists(single_html):
                os.remove(single_html)
            os.remove(single_report)

        # Create table for display
        table = PrettyTable()
        table.field_names = [
            "ID",
            "Module",
            "Pass",
            "Fail",
            "Skipped",
            "Error",
            "Time",
            "Report Link",
        ]
        table.align["Module"] = "l"
        table.align["Report Link"] = "l"

        count: defaultdict[str, int | float] = defaultdict(int)
        last_id = 0

        # Iterate through all completed XML reports
        for file in sorted(glob.glob(os.path.join(report_dir, "*.xml"))):
            # Skip skip_list.xml
            if file == os.path.join(
                session_dir, "logs/skip_list.xml"
            ):  # pragma: no cover
                continue

            try:
                testsuites = ElementTree.parse(file).getroot()
            except ElementTree.ParseError:
                logger.warning(f"[Report] Failed to parse {file}: invalid XML")
                continue
            testsuite = testsuites.find("testsuite")

            if testsuite is None:
                continue

            test_failures = int(testsuite.attrib.get("failures", 0))
            test_skipped = int(testsuite.attrib.get("skipped", 0))
            test_errors = int(testsuite.attrib.get("errors", 0))
            test_time = float(testsuite.attrib.get("time", 0))
            test_total = int(testsuite.attrib.get("tests", 0))
            test_passes = test_total - test_failures - test_skipped

            count["modules"] += 1
            count["total"] += test_total
            count["passes"] += max(test_passes, 0)
            count["failures"] += test_failures
            count["skipped"] += test_skipped
            count["errors"] += test_errors
            count["time"] += test_time

            # Extract testrun ID from filename (format: XXX_module.xml)
            m = re.search(r"([^/]+/)?([0-9]{3})_\w+", file)
            testrun_id = m.group(2) if m else "000"
            last_id = max(last_id, int(testrun_id))

            # Get relative path from report directory
            rel_file = file.replace(report_dir + "/", "")
            rel_html = rel_file.replace(".xml", ".html")

            table.add_row(
                [
                    testrun_id,
                    os.path.basename(file).replace(".xml", ""),
                    test_passes,
                    test_failures,
                    test_skipped,
                    test_errors,
                    f"{test_time:.2f}",
                    rel_html,
                ]
            )

        # Add summary row
        summary_id = f"{int(last_id) + 1:03d}"
        summary_row = [
            summary_id,
            "Summary",
            count["passes"],
            count["failures"],
            count["skipped"],
            count["errors"],
            f"{count['time']:.2f}",
            "report.html",
        ]
        table.add_row(summary_row)

        # Generate text summary
        total_summary = (
            f"[RESULT_SUMMARY] total:{count['total']} "
            f"passes:{count['passes']} failures:{count['failures']} "
            f"skipped:{count['skipped']} errors:{count['errors']} "
            f"time:{count['time']:.2f} modules:{count['modules']}"
        )
        result_summary = f"{table}\n{total_summary}"

        # IMPORTANT: Output to console
        print("\n\n")
        print(result_summary)

        # Save text version
        with open(os.path.join(report_dir, "result_summary.txt"), "w") as f:
            f.write(result_summary)

        # Generate HTML version with hyperlinks
        for row in table._rows:
            report_link = row[-1]
            row[-1] = f"<a href='{report_link}'>{report_link}</a>"

        with open(os.path.join(report_dir, "result_summary.html"), "w") as f:
            html_str = table.get_html_string(format=True)
            f.write(html.unescape(html_str))

        logger.info(
            f"[Report] Generated result summary - Modules: "
            f"{count['modules']}, Pass: {count['passes']}, "
            f"Fail: {count['failures']}"
        )
