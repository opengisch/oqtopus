"""Test to ensure bundled libraries are imported correctly."""

import ast
from pathlib import Path


def test_no_direct_bundled_lib_imports():
    """
    Ensure that pum and pgserviceparser are never imported directly.
    They should always be imported from oqtopus.libs to use the bundled versions.
    """
    oqtopus_dir = Path(__file__).parent.parent / "oqtopus"
    forbidden_imports = ["pum", "pgserviceparser"]
    violations = []

    libs_dir = oqtopus_dir / "libs"

    # Scan all Python files in the oqtopus directory
    for py_file in oqtopus_dir.rglob("*.py"):
        # Skip files inside the bundled lib directories (third-party code)
        if py_file.is_relative_to(libs_dir):
            continue

        try:
            with open(py_file, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))

            for node in ast.walk(tree):
                # Check for "import pum" or "import pgserviceparser"
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden_imports or any(
                            alias.name.startswith(f"{lib}.") for lib in forbidden_imports
                        ):
                            violations.append(
                                f"{py_file.relative_to(oqtopus_dir.parent)}: "
                                f"Direct import '{alias.name}' found at line {node.lineno}"
                            )

                # Check for "from pum import ..." or "from pgserviceparser import ..."
                elif isinstance(node, ast.ImportFrom):
                    if node.module in forbidden_imports or any(
                        node.module and node.module.startswith(f"{lib}.")
                        for lib in forbidden_imports
                    ):
                        violations.append(
                            f"{py_file.relative_to(oqtopus_dir.parent)}: "
                            f"Direct import 'from {node.module}' found at line {node.lineno}"
                        )

        except SyntaxError:
            # Skip files with syntax errors (might be templates or non-Python)
            continue

    if violations:
        error_msg = (
            "Found direct imports of bundled libraries. "
            "Please use 'from ..libs.pum import ...' or 'from ..libs.pgserviceparser import ...' instead:\n"
            + "\n".join(violations)
        )
        raise AssertionError(error_msg)
