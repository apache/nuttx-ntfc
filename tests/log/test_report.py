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

"""Tests for NTFC report generation module."""

import os
import tempfile
from xml.etree.ElementTree import Element, ElementTree, SubElement

from ntfc.log.report import Reporter


def create_test_xml(
    filename: str,
    tests: int = 10,
    passes: int = 8,
    failures: int = 2,
    skipped: int = 0,
    errors: int = 0,
    time: float = 1.5,
) -> str:
    """Create a test JUnit XML file."""
    testsuites = Element("testsuites")
    testsuite = SubElement(testsuites, "testsuite")
    testsuite.set("tests", str(tests))
    testsuite.set("failures", str(failures))
    testsuite.set("skipped", str(skipped))
    testsuite.set("errors", str(errors))
    testsuite.set("time", str(time))
    testsuite.set("name", os.path.basename(filename).replace(".xml", ""))

    tree = ElementTree(testsuites)
    tree.write(filename)
    return filename


def test_generate_result_summary_with_single_xml_file():
    """Test generate_result_summary with a single XML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        # Create test XML file directly in report_dir
        xml_file = os.path.join(report_dir, "001_test.xml")
        create_test_xml(xml_file, tests=10, passes=8, failures=2)

        # Call generate_result_summary - should not raise
        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        # Verify summary files were created in report_dir
        assert os.path.exists(os.path.join(report_dir, "result_summary.txt"))
        assert os.path.exists(os.path.join(report_dir, "result_summary.html"))


def test_generate_result_summary_with_multiple_files():
    """Test generate_result_summary aggregates multiple XML files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        # Create multiple test XML files in report_dir
        xml_file1 = os.path.join(report_dir, "001_module1.xml")
        xml_file2 = os.path.join(report_dir, "002_module2.xml")
        create_test_xml(xml_file1, tests=10, passes=8, failures=2)
        create_test_xml(xml_file2, tests=5, passes=5, failures=0)

        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        # Verify both summary files created and contain results
        summary_file = os.path.join(report_dir, "result_summary.txt")
        assert os.path.exists(summary_file)
        with open(summary_file) as f:
            content = f.read()
            # Should have summary with passes and failures
            assert "passes:" in content or "Pass" in content


def test_generate_result_summary_with_skipped_tests():
    """Test generate_result_summary with skipped tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        xml_file = os.path.join(report_dir, "001_test.xml")
        create_test_xml(
            xml_file, tests=10, passes=5, failures=0, skipped=5, errors=0
        )

        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        summary_file = os.path.join(report_dir, "result_summary.txt")
        with open(summary_file) as f:
            content = f.read()
            assert "skipped" in content


def test_generate_result_summary_with_errors():
    """Test generate_result_summary with test errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        xml_file = os.path.join(report_dir, "001_test.xml")
        create_test_xml(xml_file, tests=10, passes=7, failures=2, errors=1)

        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        summary_file = os.path.join(report_dir, "result_summary.txt")
        with open(summary_file) as f:
            content = f.read()
            assert "errors" in content


def test_generate_result_summary_skips_skip_list():
    """Test generate_result_summary ignores skip_list.xml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        logs_dir = os.path.join(tmpdir, "logs")
        os.makedirs(report_dir)
        os.makedirs(logs_dir)

        # Create skip_list.xml which should be ignored
        skip_list_file = os.path.join(logs_dir, "skip_list.xml")
        create_test_xml(skip_list_file, tests=5, passes=5)

        # Create actual test file in report_dir
        xml_file = os.path.join(report_dir, "001_test.xml")
        create_test_xml(xml_file, tests=10, passes=8, failures=2)

        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        summary_file = os.path.join(report_dir, "result_summary.txt")
        with open(summary_file) as f:
            content = f.read()
            # Verify summary was created (skip_list should be ignored)
            assert os.path.exists(summary_file)
            assert "RESULT_SUMMARY" in content or "Summary" in content


def test_generate_result_summary_with_invalid_xml():
    """Test generate_result_summary handles invalid XML gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        # Create invalid XML file in report_dir
        invalid_xml = os.path.join(report_dir, "001_invalid.xml")
        with open(invalid_xml, "w") as f:
            f.write("not valid xml content")

        # Should not raise exception
        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)


def test_generate_result_summary_missing_testsuite():
    """Test generate_result_summary with XML missing testsuite element."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        # Create XML without testsuite element in report_dir
        xml_file = os.path.join(report_dir, "001_test.xml")
        testsuites = Element("testsuites")
        tree = ElementTree(testsuites)
        tree.write(xml_file)

        # Should handle gracefully
        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)


def test_generate_result_summary_html_output():
    """Test generate_result_summary generates HTML with hyperlinks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        xml_file = os.path.join(report_dir, "001_test.xml")
        create_test_xml(xml_file, tests=10, passes=8, failures=2)

        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        # Check HTML file exists in report_dir and contains hyperlinks
        html_file = os.path.join(report_dir, "result_summary.html")
        assert os.path.exists(html_file)

        with open(html_file) as f:
            html_content = f.read()
            assert "<a href=" in html_content


def test_generate_result_summary_with_nested_directories():
    """Test generate_result_summary with XML files in nested directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # report_dir is created by generate_result_summary itself
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        xml_file = os.path.join(report_dir, "001_test.xml")
        create_test_xml(xml_file, tests=10, passes=8, failures=2)

        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        # Summary should be in report_dir
        summary_file = os.path.join(report_dir, "result_summary.txt")
        assert os.path.exists(summary_file)


def test_generate_result_summary_exception_handling():
    """Test generate_result_summary handles exceptions gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Call with valid but empty directory (no XMLs anywhere)
        # Should not raise even with no XML files
        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)


def test_generate_result_summary_with_zero_time():
    """Test generate_result_summary with zero test execution time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        xml_file = os.path.join(report_dir, "001_test.xml")
        create_test_xml(xml_file, tests=5, passes=5, time=0.0)

        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        summary_file = os.path.join(report_dir, "result_summary.txt")
        with open(summary_file) as f:
            content = f.read()
            # Should handle zero time properly
            assert "time:" in content


def test_generate_result_summary_with_large_time():
    """Test generate_result_summary with large test execution time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        xml_file = os.path.join(report_dir, "001_test.xml")
        create_test_xml(xml_file, tests=5, passes=5, time=3600.5)

        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        summary_file = os.path.join(report_dir, "result_summary.txt")
        assert os.path.exists(summary_file)


def test_generate_result_summary_complex_scenario():
    """Test generate_result_summary with complex scenario."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = os.path.join(tmpdir, "report")
        os.makedirs(report_dir)

        # Create multiple files with varying results in report_dir
        create_test_xml(
            os.path.join(report_dir, "001_module1.xml"),
            tests=20,
            passes=18,
            failures=2,
            skipped=0,
            errors=0,
        )
        create_test_xml(
            os.path.join(report_dir, "002_module2.xml"),
            tests=15,
            passes=12,
            failures=2,
            skipped=1,
            errors=0,
        )
        create_test_xml(
            os.path.join(report_dir, "003_module3.xml"),
            tests=10,
            passes=8,
            failures=1,
            skipped=0,
            errors=1,
        )

        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        # Verify all files were processed and summary created
        summary_file = os.path.join(report_dir, "result_summary.txt")
        assert os.path.exists(summary_file)
        with open(summary_file) as f:
            content = f.read()
            # Should contain summary information
            assert "RESULT_SUMMARY" in content or "Summary" in content


def test_split_xml_by_module():
    """Test splitting a single XML report into per-module files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a single XML file with tests from multiple modules
        xml_file = os.path.join(tmpdir, "report.xml")
        testsuites = Element("testsuites")
        testsuite = SubElement(testsuites, "testsuite")
        testsuite.set("tests", "6")
        testsuite.set("failures", "1")
        testsuite.set("skipped", "0")
        testsuite.set("errors", "0")
        testsuite.set("time", "2.5")

        # Add testcases from different modules
        tc1 = SubElement(testsuite, "testcase")
        tc1.set("name", "test_one")
        tc1.set("classname", "test_module1.py::test_one")
        tc1.set("time", "1.0")

        tc2 = SubElement(testsuite, "testcase")
        tc2.set("name", "test_two")
        tc2.set("classname", "test_module1.py::test_two")
        tc2.set("time", "0.5")

        tc3 = SubElement(testsuite, "testcase")
        tc3.set("name", "test_three")
        tc3.set("classname", "test_module2.py::test_three")
        tc3.set("time", "1.0")
        failure = SubElement(tc3, "failure")
        failure.set("message", "Test failed")

        tree = ElementTree(testsuites)
        tree.write(xml_file)

        # Split the XML
        reporter = Reporter()
        module_files = reporter._split_xml_by_module(xml_file, tmpdir)

        # Should have 2 module files
        assert len(module_files) == 2
        assert "test_module1" in module_files
        assert "test_module2" in module_files

        # Verify files exist
        for module_file in module_files.values():
            assert os.path.exists(module_file)


def test_split_xml_by_module_keeps_nested_properties():
    """Test that testcase properties survive the per-module split."""
    with tempfile.TemporaryDirectory() as tmpdir:
        xml_file = os.path.join(tmpdir, "report.xml")
        testsuites = Element("testsuites")
        testsuite = SubElement(testsuites, "testsuite")
        tc = SubElement(testsuite, "testcase")
        tc.set("name", "test_one")
        tc.set("classname", "test_module1.py::test_one")
        tc.set("time", "1.0")
        props = SubElement(tc, "properties")
        prop = SubElement(props, "property")
        prop.set("name", "resources")
        prop.set("value", "{}")
        ElementTree(testsuites).write(xml_file)

        module_files = Reporter()._split_xml_by_module(xml_file, tmpdir)

        root = ElementTree(file=module_files["test_module1"]).getroot()
        found = root.findall(".//testcase/properties/property")
        assert len(found) == 1
        assert found[0].get("name") == "resources"


def test_split_xml_by_module_nonexistent_file():
    """Test _split_xml_by_module with nonexistent file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = Reporter()
        result = reporter._split_xml_by_module(
            os.path.join(tmpdir, "nonexistent.xml"), tmpdir
        )
        assert result == {}


def test_split_xml_by_module_invalid_xml():
    """Test _split_xml_by_module with invalid XML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        invalid_xml = os.path.join(tmpdir, "invalid.xml")
        with open(invalid_xml, "w") as f:
            f.write("not valid xml")

        reporter = Reporter()
        result = reporter._split_xml_by_module(invalid_xml, tmpdir)
        assert result == {}


def test_generate_html_for_module():
    """Test HTML generation for a module report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        xml_file = os.path.join(tmpdir, "test_module.xml")
        create_test_xml(xml_file, tests=5, passes=4, failures=1, errors=0)

        html_file = os.path.join(tmpdir, "test_module.html")
        reporter = Reporter()
        reporter._generate_html_for_module(xml_file, html_file)

        # Verify HTML file was created
        assert os.path.exists(html_file)

        # Verify HTML contains expected content
        with open(html_file) as f:
            html_content = f.read()
            assert "<html>" in html_content.lower()
            assert "test_module" in html_content
            assert "4" in html_content  # passed count
            assert "1" in html_content  # failed count


def test_generate_result_summary_splits_single_report():
    """Test splitting single report.xml into per-module files in report_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a single report.xml file (as pytest would) in session_dir
        single_xml = os.path.join(tmpdir, "report.xml")
        testsuites = Element("testsuites")
        testsuite = SubElement(testsuites, "testsuite")
        testsuite.set("tests", "4")
        testsuite.set("failures", "1")
        testsuite.set("errors", "0")
        testsuite.set("skipped", "0")
        testsuite.set("time", "2.0")
        testsuite.set("name", "tests")

        # Add tests from different modules
        tc1 = SubElement(testsuite, "testcase")
        tc1.set("name", "test_func1")
        tc1.set("classname", "test_module1.py::test_func1")
        tc1.set("time", "1.0")

        tc2 = SubElement(testsuite, "testcase")
        tc2.set("name", "test_func2")
        tc2.set("classname", "test_module1.py::test_func2")
        tc2.set("time", "0.5")

        tc3 = SubElement(testsuite, "testcase")
        tc3.set("name", "test_func3")
        tc3.set("classname", "test_module2.py::test_func3")
        tc3.set("time", "0.5")
        failure = SubElement(tc3, "failure")
        failure.set("message", "Assertion failed")

        tc4 = SubElement(testsuite, "testcase")
        tc4.set("name", "test_func4")
        tc4.set("classname", "test_module2.py::test_func4")
        tc4.set("time", "0.0")

        tree = ElementTree(testsuites)
        tree.write(single_xml)

        # Also create report.html (as pytest would)
        single_html = os.path.join(tmpdir, "report.html")
        with open(single_html, "w") as f:
            f.write("<html><body>test</body></html>")

        # Call generate_result_summary
        reporter = Reporter()
        reporter.generate_result_summary(tmpdir)

        # Verify single files were removed from session_dir
        assert not os.path.exists(single_xml)
        assert not os.path.exists(single_html)

        # Verify per-module files were created in report_dir
        report_dir = os.path.join(tmpdir, "report")
        module1_xml = os.path.join(report_dir, "001_test_module1.xml")
        module1_html = os.path.join(report_dir, "001_test_module1.html")
        module2_xml = os.path.join(report_dir, "002_test_module2.xml")
        module2_html = os.path.join(report_dir, "002_test_module2.html")

        assert os.path.exists(module1_xml)
        assert os.path.exists(module1_html)
        assert os.path.exists(module2_xml)
        assert os.path.exists(module2_html)

        # Verify summary files were created in report_dir
        assert os.path.exists(os.path.join(report_dir, "result_summary.txt"))
        assert os.path.exists(os.path.join(report_dir, "result_summary.html"))
