"""Integration tests for the ModuleWidget.

These tests exercise the oqtopus GUI by programmatically driving the
ModuleWidget: setting a module package (from a local directory), connecting
to a database, and clicking install/upgrade/uninstall buttons.

Requires:
    - PyQt5 or PyQt6 (QGIS is NOT required — uses the standalone shim)
    - A running PostgreSQL server with pg_service 'oqtopus_test'
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg
import pytest

# ---------------------------------------------------------------------------
# Bootstrap the qgis.PyQt shim (same approach as oqtopus.py) so that
# oqtopus modules can be imported without a real QGIS installation.
# ---------------------------------------------------------------------------
if "qgis" not in sys.modules:
    try:
        pyqt_core = __import__("PyQt6.QtCore", fromlist=[""])
        pyqt_gui = __import__("PyQt6.QtGui", fromlist=[""])
        pyqt_network = __import__("PyQt6.QtNetwork", fromlist=[""])
        pyqt_widgets = __import__("PyQt6.QtWidgets", fromlist=[""])
        pyqt_uic = __import__("PyQt6.uic", fromlist=[""])
    except ModuleNotFoundError:
        pyqt_core = __import__("PyQt5.QtCore", fromlist=[""])
        pyqt_gui = __import__("PyQt5.QtGui", fromlist=[""])
        pyqt_network = __import__("PyQt5.QtNetwork", fromlist=[""])
        pyqt_widgets = __import__("PyQt5.QtWidgets", fromlist=[""])
        pyqt_uic = __import__("PyQt5.uic", fromlist=[""])

    qgis = types.ModuleType("qgis")
    pyqt = types.ModuleType("qgis.PyQt")
    pyqt.QtCore = pyqt_core
    pyqt.QtGui = pyqt_gui
    pyqt.QtNetwork = pyqt_network
    pyqt.QtWidgets = pyqt_widgets
    pyqt.uic = pyqt_uic

    qgis.PyQt = pyqt
    sys.modules["qgis"] = qgis
    sys.modules["qgis.PyQt"] = pyqt
    sys.modules["qgis.PyQt.QtCore"] = pyqt_core
    sys.modules["qgis.PyQt.QtGui"] = pyqt_gui
    sys.modules["qgis.PyQt.QtNetwork"] = pyqt_network
    sys.modules["qgis.PyQt.QtWidgets"] = pyqt_widgets
    sys.modules["qgis.PyQt.uic"] = pyqt_uic

# Ensure a QApplication exists (needed for Qt widgets)
from qgis.PyQt.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

from qgis.PyQt.QtCore import QEventLoop, QTimer  # noqa: E402
from qgis.PyQt.QtWidgets import QMessageBox  # noqa: E402

from oqtopus.core.module_package import ModulePackage  # noqa: E402
from oqtopus.gui.module_widget import ModuleWidget  # noqa: E402
from oqtopus.libs.pum.pum_config import PumConfig  # noqa: E402
from oqtopus.libs.pum.schema_migrations import SchemaMigrations  # noqa: E402
from oqtopus.libs.pum.upgrader import Upgrader  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_DATA_DIR = Path(__file__).parent / "data"


class _FakeModule:
    """Minimal stand-in for oqtopus.core.module.Module (which needs QNetwork)."""

    def __init__(self, name: str, id: str):
        self.name = name
        self.id = id
        self.organisation = "test"
        self.repository = "test"


def _make_module_package(source_dir: str, module: _FakeModule) -> ModulePackage:
    """Create a FROM_DIRECTORY ModulePackage pointing to a local directory."""
    pkg = ModulePackage(
        module=module,
        organisation=module.organisation,
        repository=module.repository,
        json_payload=None,
        type=ModulePackage.Type.FROM_DIRECTORY,
        name="from_directory",
    )
    pkg.source_package_dir = source_dir
    return pkg


def _wait_for_operation(widget: ModuleWidget, timeout_ms: int = 10000):
    """Block until ModuleWidget.signal_operationFinished is emitted (or timeout)."""
    if not widget.isOperationRunning():
        return
    loop = QEventLoop()
    widget.signal_operationFinished.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


def _configure_mock_dialog(cls_mock, *, roles: bool = False, suffix: str | None = None):
    """Wire up a mock InstallDialog / UpgradeDialog so it auto-accepts."""
    dialog = MagicMock()
    dialog.exec.return_value = 1  # QDialog.Accepted
    dialog.parameters.return_value = {}
    dialog.roles.return_value = roles
    dialog.roles_options.return_value = {
        "roles": roles,
        "grant": roles,
        **({"suffix": suffix} if suffix else {}),
    }
    dialog.beta_testing.return_value = False
    dialog.install_demo_data.return_value = False
    dialog.demo_data_name.return_value = None
    cls_mock.return_value = dialog
    cls_mock.DialogCode = MagicMock()
    cls_mock.DialogCode.Accepted = 1
    return dialog


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_blocking_dialogs():
    """Prevent modal dialogs from blocking tests.

    CriticalMessageBox.exec() and QMessageBox.information() will raise
    immediately instead of opening a window that waits for user input.
    """

    def _raise_on_critical_exec(self):
        raise AssertionError(f"Unexpected CriticalMessageBox: {self.text()}")

    with (
        patch(
            "oqtopus.utils.qt_utils.CriticalMessageBox.exec",
            _raise_on_critical_exec,
        ),
        patch(
            "oqtopus.gui.module_widget.QMessageBox.information",
            return_value=None,
        ),
    ):
        yield


@pytest.fixture()
def db_connection(clean_db, pg_service):
    """Provide a psycopg connection to the test database.

    Depends on clean_db so the connection is opened after cleanup
    and closed before the post-test cleanup runs.
    """
    conn = psycopg.connect(f"service={pg_service}", autocommit=False)
    yield conn
    conn.close()


@pytest.fixture()
def module_widget():
    """Create a ModuleWidget instance."""
    widget = ModuleWidget()
    yield widget
    widget.close()


@pytest.fixture()
def simple_module_package():
    """Create a ModulePackage for the simple_module test data."""
    module = _FakeModule(name="Test Module", id="oqtopus_test_module")
    source_dir = str(TEST_DATA_DIR / "simple_module")
    return _make_module_package(source_dir, module)


@pytest.fixture()
def roles_module_package():
    """Create a ModulePackage for the module_with_roles test data."""
    module = _FakeModule(name="Test Roles Module", id="oqtopus_test_roles")
    source_dir = str(TEST_DATA_DIR / "module_with_roles")
    return _make_module_package(source_dir, module)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestModuleWidgetInstall:
    """Test installing a module through the ModuleWidget."""

    def test_install_page_shown_for_new_module(
        self, module_widget, simple_module_package, db_connection
    ):
        """When a module is not installed, the install page should be shown."""
        module_widget.setModulePackage(simple_module_package)
        module_widget.setDatabaseConnection(db_connection)

        # The stacked widget should show the install page
        current_page = module_widget.moduleInfo_stackedWidget.currentWidget()
        assert current_page == module_widget.moduleInfo_stackedWidget_pageInstall

    @patch("oqtopus.gui.module_widget.InstallDialog")
    def test_install_creates_schema(
        self,
        mock_install_dialog_cls,
        module_widget,
        simple_module_package,
        db_connection,
        test_data_dir,
    ):
        """Clicking install should create the module schema in the database."""
        _configure_mock_dialog(mock_install_dialog_cls)

        module_widget.setModulePackage(simple_module_package)
        module_widget.setDatabaseConnection(db_connection)

        # Click the install button
        module_widget.moduleInfo_install_pushButton.click()

        # Wait for the background operation to finish
        _wait_for_operation(module_widget)

        # Verify the module was installed using pum API
        pum_config = PumConfig.from_yaml(
            test_data_dir / "simple_module" / "datamodel" / ".pum.yaml"
        )
        sm = SchemaMigrations(pum_config)

        # Verify the module is installed (migration table exists and has entries)
        assert sm.exists(
            db_connection
        ), "Module should be installed (pum_migrations table should exist)"

        # Verify the baseline version is set
        baseline = sm.baseline(db_connection)
        assert baseline is not None, "Baseline version should be set after install"
        assert str(baseline) == "1.1.0", f"Expected baseline 1.1.0, got {baseline}"

    @patch("oqtopus.gui.module_widget.InstallDialog")
    def test_install_shows_maintain_page_after(
        self,
        mock_install_dialog_cls,
        module_widget,
        simple_module_package,
        db_connection,
    ):
        """After installing, the widget should switch to the maintain page."""
        _configure_mock_dialog(mock_install_dialog_cls)

        module_widget.setModulePackage(simple_module_package)
        module_widget.setDatabaseConnection(db_connection)
        module_widget.moduleInfo_install_pushButton.click()
        _wait_for_operation(module_widget)

        # After install the widget refreshes and should show maintain page
        current_page = module_widget.moduleInfo_stackedWidget.currentWidget()
        assert current_page == module_widget.moduleInfo_stackedWidget_pageMaintain


class TestModuleWidgetUpgrade:
    """Test upgrading a module through the ModuleWidget."""

    @patch("oqtopus.gui.module_widget.InstallDialog")
    @patch("oqtopus.gui.module_widget.UpgradeDialog")
    def test_upgrade_bumps_version(
        self,
        mock_upgrade_dialog_cls,
        mock_install_dialog_cls,
        module_widget,
        simple_module_package,
        db_connection,
        pg_service,
    ):
        """Installing at 1.0.0 then upgrading should reach 1.1.0."""
        _configure_mock_dialog(mock_install_dialog_cls)
        _configure_mock_dialog(mock_upgrade_dialog_cls)

        module_widget.setModulePackage(simple_module_package)
        module_widget.setDatabaseConnection(db_connection)

        # Step 1: Install at version 1.0.0 (need to temporarily restrict max_version)
        # We use the operation task directly for the initial install at 1.0.0
        pum_dir = TEST_DATA_DIR / "simple_module" / "datamodel"
        cfg = PumConfig.from_yaml(pum_dir / ".pum.yaml")
        upgrader = Upgrader(cfg)
        upgrader.install(connection=db_connection, max_version="1.0.0")
        db_connection.commit()

        # Step 2: Refresh the widget to detect the installed 1.0.0
        module_widget.setDatabaseConnection(db_connection)

        # Verify upgrade page is shown (1.1.0 > 1.0.0)
        current_page = module_widget.moduleInfo_stackedWidget.currentWidget()
        assert current_page == module_widget.moduleInfo_stackedWidget_pageUpgrade

        # Step 3: Click upgrade
        module_widget.moduleInfo_upgrade_pushButton.click()
        _wait_for_operation(module_widget)

        # Verify the version was upgraded to 1.1.0
        sm = SchemaMigrations(cfg)
        with psycopg.connect(f"service={pg_service}") as conn:
            assert str(sm.baseline(conn)) == "1.1.0"


class TestModuleWidgetUninstall:
    """Test uninstalling a module through the ModuleWidget."""

    @patch("oqtopus.gui.module_widget.InstallDialog")
    @patch(
        "oqtopus.gui.module_widget.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )
    def test_uninstall_removes_module(
        self,
        mock_question,
        mock_install_dialog_cls,
        module_widget,
        simple_module_package,
        db_connection,
        pg_service,
    ):
        """Installing then uninstalling should remove the module schema."""
        _configure_mock_dialog(mock_install_dialog_cls)

        module_widget.setModulePackage(simple_module_package)
        module_widget.setDatabaseConnection(db_connection)

        # Install first
        module_widget.moduleInfo_install_pushButton.click()
        _wait_for_operation(module_widget)

        # Verify installed
        with psycopg.connect(f"service={pg_service}") as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.schemata "
                "  WHERE schema_name = 'oqtopus_test'"
                ")"
            )
            assert cur.fetchone()[0], "Schema should exist after install"

        # Now uninstall
        module_widget.uninstall_button_maintain.click()
        _wait_for_operation(module_widget)

        # Verify uninstalled - the uninstall hook runs but doesn't necessarily
        # drop the schema (depends on uninstall.sql contents)
        with psycopg.connect(f"service={pg_service}") as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_schema = 'oqtopus_test' "
                "  AND table_name = 'items'"
                ")"
            )
            assert not cur.fetchone()[0], "Table 'items' should be gone after uninstall"


class TestModuleWidgetRoles:
    """Test role management through the ModuleWidget."""

    @patch("oqtopus.gui.module_widget.InstallDialog")
    def test_install_with_roles(
        self,
        mock_install_dialog_cls,
        module_widget,
        roles_module_package,
        db_connection,
        pg_service,
    ):
        """Installing a module with roles=True should create database roles."""
        _configure_mock_dialog(mock_install_dialog_cls, roles=True)

        module_widget.setModulePackage(roles_module_package)
        module_widget.setDatabaseConnection(db_connection)

        module_widget.moduleInfo_install_pushButton.click()
        _wait_for_operation(module_widget)

        # Verify roles were created
        with psycopg.connect(f"service={pg_service}") as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT rolname FROM pg_roles "
                "WHERE rolname IN ('oqtopus_test_viewer', 'oqtopus_test_editor') "
                "ORDER BY rolname;"
            )
            roles = [row[0] for row in cur.fetchall()]
            assert "oqtopus_test_editor" in roles
            assert "oqtopus_test_viewer" in roles

    @patch("oqtopus.gui.roles_manage_dialog.RolesCreateDialog")
    @patch("oqtopus.gui.module_widget.InstallDialog")
    def test_roles_button_grants_permissions(
        self,
        mock_install_dialog_cls,
        mock_roles_dialog_cls,
        module_widget,
        roles_module_package,
        db_connection,
        pg_service,
    ):
        """Clicking Manage roles → Create and grant roles should create and grant roles."""
        from oqtopus.gui.roles_manage_dialog import RolesManageDialog

        # Install without roles first
        _configure_mock_dialog(mock_install_dialog_cls)

        # Configure the RolesCreateDialog mock (shown inside RolesManageDialog)
        mock_roles_dialog = MagicMock()
        mock_roles_dialog.exec.return_value = 1
        mock_roles_dialog.roles_options.return_value = {
            "roles": True,
            "grant": True,
        }
        mock_roles_dialog_cls.return_value = mock_roles_dialog
        mock_roles_dialog_cls.DialogCode = MagicMock()
        mock_roles_dialog_cls.DialogCode.Accepted = 1

        module_widget.setModulePackage(roles_module_package)
        module_widget.setDatabaseConnection(db_connection)

        module_widget.moduleInfo_install_pushButton.click()
        _wait_for_operation(module_widget)

        # Patch RolesManageDialog.exec to trigger create/grant, then close
        # Also patch QMessageBox.information to avoid blocking
        def patched_exec(dialog_self):
            dialog_self._on_create_grant_roles()
            return 1

        with patch.object(RolesManageDialog, "exec", patched_exec), patch(
            "oqtopus.gui.roles_manage_dialog.QMessageBox"
        ):
            module_widget.moduleInfo_check_roles_pushButton.click()

        # Verify viewer has SELECT permission
        with psycopg.connect(f"service={pg_service}") as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT has_table_privilege("
                "  'oqtopus_test_viewer', 'oqtopus_test_roles.items', 'SELECT'"
                ");"
            )
            assert cur.fetchone()[0], "Viewer should have SELECT on items"


class TestModuleWidgetUninstallDisabled:
    """Test uninstall button behavior for modules without uninstall functionality."""

    @patch("oqtopus.gui.module_widget.InstallDialog")
    def test_uninstall_disabled_for_module_without_uninstall(
        self, mock_install_dialog_cls, module_widget, db_connection, roles_module_package
    ):
        """Uninstall button should be disabled for modules without uninstall config."""
        _configure_mock_dialog(mock_install_dialog_cls)

        module_widget.setModulePackage(roles_module_package)
        module_widget.setDatabaseConnection(db_connection)

        # Install the module
        module_widget.moduleInfo_install_pushButton.click()
        _wait_for_operation(module_widget)

        # After install, the widget should be on the maintain page
        current_page = module_widget.moduleInfo_stackedWidget.currentWidget()
        assert current_page == module_widget.moduleInfo_stackedWidget_pageMaintain

        # Check that the uninstall button on maintain page is disabled
        assert not module_widget.uninstall_button_maintain.isEnabled()

        # Verify tooltip indicates uninstall is not available
        tooltip = module_widget.uninstall_button_maintain.toolTip()
        assert "not available" in tooltip.lower()
