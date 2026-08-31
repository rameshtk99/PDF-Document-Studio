#!/usr/bin/env python3
"""
Stage 14: Comprehensive Testing & Validation

Final validation suite for the PDF Footer editor project.
This script runs the real project tests and smoke checks that confirm
compatibility across the completed Phase 1 implementation.
"""

import os
import subprocess
import sys
import py_compile
from pathlib import Path

# TESTS_DIR is where this script and its sibling test_stageN.py scripts
# live; ROOT is the true project root (main.py, models/, pdf/, app/,
# utils/, and the test2.pdf/"Ximeki MEs 82.pdf" fixtures) one level up.
# Sibling scripts are invoked with cwd=str(ROOT) so their own bare
# "test2.pdf"-style literals keep resolving correctly.
TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# This script also imports project packages directly (see Test 4 below),
# so it needs the true project root on sys.path -- previously implicit
# when this script lived at the root itself.
sys.path.insert(0, str(ROOT))


def print_section(title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def run_python_script(script_name: str):
    script_path = TESTS_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_name}")

    print(f"Running {script_name}...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    if result.stdout:
        print(result.stdout.encode("ascii", "backslashreplace").decode("ascii"))
    if result.stderr:
        print(result.stderr.encode("ascii", "backslashreplace").decode("ascii"))

    if result.returncode != 0:
        raise RuntimeError(f"{script_name} failed with exit code {result.returncode}")


def test_syntax_validation():
    """Compile the project modules to confirm there are no syntax errors."""
    print_section("Test 1: Syntax Validation")

    files_to_compile = [
        ROOT / "main.py",
        TESTS_DIR / "test_stage2.py",
        TESTS_DIR / "test_stage4.py",
        TESTS_DIR / "test_stage5.py",
        TESTS_DIR / "test_stage6.py",
        TESTS_DIR / "test_stage7.py",
        TESTS_DIR / "test_stage8.py",
        TESTS_DIR / "test_stage9.py",
        TESTS_DIR / "test_stage10.py",
        TESTS_DIR / "test_stage11.py",
        TESTS_DIR / "test_stage12.py",
        TESTS_DIR / "test_stage13.py",
        TESTS_DIR / "test_stage14.py",
        ROOT / "models" / "models.py",
        ROOT / "pdf" / "pdf_loader.py",
        ROOT / "pdf" / "image_manager.py",
        ROOT / "app" / "undo_redo.py",
        ROOT / "utils" / "project_manager.py",
    ]

    for path in files_to_compile:
        py_compile.compile(str(path), doraise=True)

    print("OK: All project Python files compile successfully")
    return True


def test_cli_regression_smoke():
    """Verify the main CLI still works exactly as expected."""
    print_section("Test 2: CLI Regression Smoke")

    output_file = OUTPUT_DIR / "stage14_validation_output.pdf"
    if output_file.exists():
        output_file.unlink()

    cmd = [
        sys.executable,
        str(ROOT / "main.py"),
        "--input",
        "test2.pdf",
        "--output",
        str(output_file),
        "--footer",
        "Stage 14|Validation",
        "--font",
        "Arial",
        "--size",
        "13",
    ]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if result.stdout:
        print(result.stdout.encode("ascii", "backslashreplace").decode("ascii"))
    if result.stderr:
        print(result.stderr.encode("ascii", "backslashreplace").decode("ascii"))

    assert result.returncode == 0, "CLI smoke test failed"
    assert output_file.exists(), "CLI output PDF was not created"

    print("OK: CLI smoke test passed")
    return True


def test_stage_scripts_integration():
    """Run the complete set of prior stage scripts to confirm end-to-end compatibility."""
    print_section("Test 3: Integration Validation")

    stage_scripts = [
        "test_stage2.py",
        "test_stage4.py",
        "test_stage5.py",
        "test_stage6.py",
        "test_stage7.py",
        "test_stage8.py",
        "test_stage9.py",
        "test_stage10.py",
        "test_stage11.py",
        "test_stage12.py",
        "test_stage13.py",
    ]

    for script_name in stage_scripts:
        run_python_script(script_name)

    print("OK: All prior stage test suites passed")
    return True


def test_project_integrity_and_round_trip():
    """Validate project persistence and the document model remain consistent."""
    print_section("Test 4: Project Integrity")

    from models.models import Document, PageConfig, FooterConfig, PageObject, PageRef
    from utils.project_manager import ProjectManager

    doc = Document(pdf_path="test2.pdf")
    # Built by hand rather than via PDFLoader (which populates doc.pages
    # itself) -- doc.pages must be populated to match page_count, the same
    # invariant every real load path (PDFLoader, ProjectManager) upholds,
    # since it's now the source of truth ProjectManager serializes.
    doc.pages = [PageRef(source_path="test2.pdf", source_index=i, width=612, height=792)
                 for i in range(2)]
    doc.page_count = 2
    page_cfg = PageConfig(page_number=0)
    page_cfg.footer_config = FooterConfig(
        text_columns=[("Stage 14", "Validation")],
        font_name="Arial",
        font_size=12,
    )
    page_cfg.objects.append(
        PageObject(
            id="obj_1",
            type="image",
            x=10,
            y=20,
            width=100,
            height=80,
            opacity=80,
            z_index=2,
            properties={"source": "sample.png"},
        )
    )
    doc.page_configs[0] = page_cfg

    assert doc.page_count == 2, "Document page count not preserved"
    assert doc.page_configs[0].footer_config.font_name == "Arial", "Footer config mismatch"
    assert doc.page_configs[0].objects[0].id == "obj_1", "Image object mismatch"

    project_file = OUTPUT_DIR / "stage14_temp_project.pdfeditor"
    if project_file.exists():
        project_file.unlink()

    manager = ProjectManager(project_file)
    manager.document = doc
    assert manager.save(), "Project save failed"

    loaded = manager.load()
    assert loaded.page_count == 2, "Loaded project page count mismatch"
    assert loaded.page_configs[0].footer_config.text_columns[0][0] == "Stage 14", "Footer serialization mismatch"
    assert loaded.page_configs[0].objects[0].id == "obj_1", "Loaded image object mismatch"

    if project_file.exists():
        project_file.unlink()

    print("OK: Project integrity and round-trip validation passed")
    return True


def main():
    print("\n" + "=" * 70)
    print("STAGE 14 TEST SUITE: FINAL VALIDATION")
    print("=" * 70)

    tests = [
        test_syntax_validation,
        test_cli_regression_smoke,
        test_stage_scripts_integration,
        test_project_integrity_and_round_trip,
    ]

    passed = 0
    total = len(tests)
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as exc:
            print(f"FAIL: {test.__name__} failed: {exc}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("=" * 70)

    if passed == total:
        print("FINAL VALIDATION PASSED - Project ready for completion")
        return 0

    print("FINAL VALIDATION FAILED - review failing checks")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
