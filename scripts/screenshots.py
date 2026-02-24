#!/usr/bin/env python3
"""Take screenshots of the oqtopus GUI for documentation.

Usage:
    QT_QPA_PLATFORM=offscreen python scripts/screenshots.py
    # or with a display:
    python scripts/screenshots.py

This script drives the full GUI workflow against a real database
(PG service ``tww-test``) and captures screenshots at each step:

01. Select PG service
02. Select module "TEKSI Wastewater"
03. Select version 2025.0.2 and prepare package
04. Install parameters dialog
05. Installation in progress
06. Load development branches
07. Select dev branch "main" and prepare package
08. Upgrade parameters dialog
09. Upgrade in progress
10. Role management dialog
11. Uninstall (cleanup, no screenshot)

Screenshots are saved to docs/docs/assets/images/screenshots/.
"""

import sys
import traceback

# ---------------------------------------------------------------------------
# Bootstrap qgis.PyQt shim (same as tests / standalone entry point)
# ---------------------------------------------------------------------------
import types
from pathlib import Path

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

from qgis.PyQt.QtCore import QEventLoop, QPoint, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import QApplication, QMessageBox

_app = QApplication.instance() or QApplication(sys.argv)

from oqtopus.core.module_package import ModulePackage  # noqa: E402
from oqtopus.gui.install_dialog import InstallDialog  # noqa: E402
from oqtopus.gui.main_dialog import MainDialog  # noqa: E402
from oqtopus.gui.roles_manage_dialog import RolesManageDialog  # noqa: E402
from oqtopus.gui.upgrade_dialog import UpgradeDialog  # noqa: E402
from oqtopus.utils.plugin_utils import PluginUtils  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path("docs/docs/assets/images/screenshots")

PG_SERVICE = "oqtopus_test"
MODULE_ID = "tww"
INSTALL_VERSION = "2025.0.2"
DEV_BRANCH = "main"

# Click marker style
MARKER_COLOR = QColor(255, 50, 50, 200)  # semi-transparent red
MARKER_RADIUS = 18
MARKER_PEN_WIDTH = 3
MARKER_CROSSHAIR_LEN = 8  # length of the crosshair arms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _grab(widget, filename: str, click_targets: list[QPoint] | None = None):
    """Grab a screenshot of *widget* and save it.

    Args:
        widget: The QWidget to capture.
        filename: File name (e.g. "main_dialog.png").
        click_targets: Optional list of QPoint positions (relative to *widget*)
            where a click-marker circle should be drawn.
    """
    _app.processEvents()

    pixmap: QPixmap = widget.grab()

    if click_targets:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(MARKER_COLOR, MARKER_PEN_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for pt in click_targets:
            painter.drawEllipse(pt, MARKER_RADIUS, MARKER_RADIUS)
            r = MARKER_CROSSHAIR_LEN
            painter.drawLine(pt.x() - r, pt.y(), pt.x() + r, pt.y())
            painter.drawLine(pt.x(), pt.y() - r, pt.x(), pt.y() + r)

        painter.end()

    path = OUTPUT_DIR / filename
    pixmap.save(str(path))
    print(f"    saved {path}")


def _widget_center_in(widget, ancestor) -> QPoint:
    """Return the center of *widget* mapped to *ancestor*'s coordinate system."""
    local_center = QPoint(widget.width() // 2, widget.height() // 2)
    return widget.mapTo(ancestor, local_center)


def _wait_for_signal(signal, timeout_ms=60_000):
    """Block until *signal* fires or *timeout_ms* elapses."""
    loop = QEventLoop()
    signal.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


def _process_events_for(ms: int):
    """Spin the event loop for *ms* milliseconds."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _close_message_boxes():
    """Accept / close any visible QMessageBox (e.g. success popups)."""
    for w in _app.topLevelWidgets():
        if isinstance(w, QMessageBox) and w.isVisible():
            w.accept()


# ---------------------------------------------------------------------------
# Accessors (shorthands for name-mangled private attributes)
# ---------------------------------------------------------------------------


def _db_widget(dialog: MainDialog):
    return dialog._MainDialog__databaseConnectionWidget


def _mod_sel(dialog: MainDialog):
    return dialog._MainDialog__moduleSelectionWidget


def _mod_widget(dialog: MainDialog):
    return dialog._MainDialog__moduleWidget


def _pum_config(dialog: MainDialog):
    return _mod_widget(dialog)._ModuleWidget__pum_config


def _module_package(dialog: MainDialog):
    return _mod_widget(dialog)._ModuleWidget__current_module_package


def _connection(dialog: MainDialog):
    return _mod_widget(dialog)._ModuleWidget__database_connection


def _operation_task(dialog: MainDialog):
    return _mod_widget(dialog)._ModuleWidget__operation_task


# ---------------------------------------------------------------------------
# Workflow steps
# ---------------------------------------------------------------------------


def step_01_select_service(dialog: MainDialog):
    """Step 01 – Select PG service and screenshot the connected state."""
    db = _db_widget(dialog)
    combo = db.db_services_comboBox
    idx = combo.findText(PG_SERVICE)
    if idx < 0:
        raise RuntimeError(f"PG service '{PG_SERVICE}' not found in combobox")
    print(f"    selecting service '{PG_SERVICE}' (index {idx})...")
    combo.setCurrentIndex(idx)
    _app.processEvents()
    print(f"    connected to database: {db.db_database_label.text()}")

    # Verify the database is clean: check for leftover TWW schemas
    conn = _connection(dialog)
    if conn is not None:
        _TWW_SCHEMAS = ("tww_app", "tww_od", "tww_vl", "tww_sys")
        existing = []
        for schema in _TWW_SCHEMAS:
            row = conn.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (schema,)
            ).fetchone()
            if row:
                existing.append(schema)
        if existing:
            print(f"    \u26a0\ufe0f  found leftover schemas: {', '.join(existing)}")
            answer = input("    drop them before continuing? [y/N] ").strip().lower()
            if answer != "y":
                raise RuntimeError("Aborted \u2014 leftover schemas must be dropped first.")
            for schema in existing:
                print(f"    dropping {schema}...")
                conn.execute(f"DROP SCHEMA {schema} CASCADE")
            conn.commit()
            print("    schemas dropped")
        else:
            print("    database is clean (no leftover schemas)")

    click_pos = _widget_center_in(combo, dialog)
    _grab(dialog, "01_service_selected.png", click_targets=[click_pos])


def step_02_select_module(dialog: MainDialog):
    """Step 02 – Select the TEKSI Wastewater module and wait for versions to load."""
    ms = _mod_sel(dialog)
    print(f"    selecting module '{MODULE_ID}'...")
    if not ms.selectModuleById(MODULE_ID):
        raise RuntimeError(f"Module '{MODULE_ID}' not found in combobox")

    # selectModuleById triggers __moduleChanged which loads versions async
    print("    waiting for versions to load from GitHub...")
    _wait_for_signal(ms.signal_loadingFinished, timeout_ms=30_000)
    _app.processEvents()
    n_versions = ms.module_package_comboBox.count()
    print(f"    versions loaded ({n_versions} entries in combobox)")

    module_combo = ms.module_module_comboBox
    click_pos = _widget_center_in(module_combo, dialog)
    _grab(dialog, "02_module_selected.png", click_targets=[click_pos])


def step_03_select_version(dialog: MainDialog):
    """Step 03 – Select the install version and wait for the package to be prepared."""
    ms = _mod_sel(dialog)
    combo = ms.module_package_comboBox

    # Find the matching version
    found = False
    for i in range(combo.count()):
        pkg = combo.itemData(i)
        if isinstance(pkg, ModulePackage) and pkg.name == INSTALL_VERSION:
            combo.setCurrentIndex(i)
            found = True
            break
    if not found:
        raise RuntimeError(f"Version '{INSTALL_VERSION}' not found in package combobox")

    # Selecting a version starts the PackagePrepareTask
    print(f"    downloading and preparing package for {INSTALL_VERSION}...")
    _wait_for_signal(ms.signal_loadingFinished, timeout_ms=120_000)
    _app.processEvents()
    print("    package ready")

    click_pos = _widget_center_in(combo, dialog)
    _grab(dialog, "03_version_selected.png", click_targets=[click_pos])


def step_04_install_dialog(dialog: MainDialog):
    """Step 04 – Create and screenshot the install parameters dialog."""
    mw = _mod_widget(dialog)
    cfg = _pum_config(dialog)
    pkg = _module_package(dialog)
    if cfg is None:
        raise RuntimeError("PUM config not loaded — was the package prepared?")

    target_version = cfg.last_version()
    demo_data = cfg.demo_data()
    standard_params = mw._ModuleWidget__standard_params
    app_only_params = mw._ModuleWidget__app_only_params
    print(f"    target version: {target_version}")
    print(f"    parameters: {len(standard_params)} standard, {len(app_only_params)} app-only")

    install_dlg = InstallDialog(
        pkg,
        standard_params,
        app_only_params,
        target_version,
        demo_data if demo_data else None,
        dialog,
    )
    install_dlg.show()
    _app.processEvents()

    _grab(install_dlg, "04_install_dialog.png")

    # Collect parameters then close (we'll start the operation manually)
    params = install_dlg.parameters()
    options = {
        **install_dlg.roles_options(),
        "beta_testing": install_dlg.beta_testing(),
        "allow_multiple_modules": PluginUtils.get_allow_multiple_modules(),
        "install_demo_data": install_dlg.install_demo_data(),
        "demo_data_name": install_dlg.demo_data_name(),
    }
    install_dlg.close()
    return params, options


def step_05_install_run(dialog: MainDialog, params: dict, options: dict):
    """Step 05 – Start the install operation, screenshot progress, and wait for completion."""
    mw = _mod_widget(dialog)
    task = _operation_task(dialog)

    # Start install
    print("    starting install operation...")
    mw._ModuleWidget__startOperation("install", params, options)

    # Wait a bit then capture progress
    print("    capturing progress screenshot (2s delay)...")
    _process_events_for(2_000)

    install_btn = mw.moduleInfo_install_pushButton
    click_pos = _widget_center_in(install_btn, dialog)
    _grab(dialog, "05_install_in_progress.png", click_targets=[click_pos])

    # Wait for the operation to finish
    print("    waiting for install to complete...")
    _wait_for_signal(task.signalFinished, timeout_ms=300_000)
    _process_events_for(200)
    _close_message_boxes()
    _app.processEvents()
    print("    install finished")


def step_06_load_dev_branches(dialog: MainDialog):
    """Step 06 – Trigger loading of development branches."""
    ms = _mod_sel(dialog)
    combo = ms.module_package_comboBox

    # Get the Module object so we can wait on its signal
    module = ms.module_module_comboBox.currentData()

    # Find the "Load pre-releases and development branches" special item
    for i in range(combo.count()):
        if combo.itemData(i) == ms.module_package_SPECIAL_LOAD_DEVELOPMENT:
            combo.setCurrentIndex(i)
            break
    else:
        raise RuntimeError("'Load pre-releases and development branches' item not found")

    # Dev-branch loading emits signal_developmentVersionsLoaded, not signal_loadingFinished
    print("    waiting for development versions to load from GitHub...")
    _wait_for_signal(module.signal_developmentVersionsLoaded, timeout_ms=30_000)
    _app.processEvents()
    n_items = combo.count()
    print(f"    development versions loaded ({n_items} entries in combobox)")

    click_pos = _widget_center_in(combo, dialog)
    _grab(dialog, "06_dev_branches_loaded.png", click_targets=[click_pos])


def step_07_select_dev_branch(dialog: MainDialog):
    """Step 07 – Select the development branch and wait for package preparation."""
    ms = _mod_sel(dialog)
    combo = ms.module_package_comboBox

    found = False
    for i in range(combo.count()):
        pkg = combo.itemData(i)
        if isinstance(pkg, ModulePackage) and pkg.name == DEV_BRANCH:
            combo.setCurrentIndex(i)
            found = True
            break
    if not found:
        raise RuntimeError(f"Branch '{DEV_BRANCH}' not found in package combobox")

    print(f"    downloading and preparing package for branch '{DEV_BRANCH}'...")
    _wait_for_signal(ms.signal_loadingFinished, timeout_ms=120_000)
    _app.processEvents()
    print("    dev package ready")

    click_pos = _widget_center_in(combo, dialog)
    _grab(dialog, "07_dev_branch_selected.png", click_targets=[click_pos])


def step_08_upgrade_dialog(dialog: MainDialog):
    """Step 08 – Create and screenshot the upgrade parameters dialog."""
    _mod_widget(dialog)
    cfg = _pum_config(dialog)
    pkg = _module_package(dialog)
    conn = _connection(dialog)
    if cfg is None:
        raise RuntimeError("PUM config not loaded for upgrade")

    from oqtopus.libs.pum.schema_migrations import SchemaMigrations

    sm = SchemaMigrations(cfg)
    all_params = cfg.parameters()
    standard_params = [p for p in all_params if not p.app_only]
    app_only_params = [p for p in all_params if p.app_only]
    target_version = cfg.last_version()

    installed_parameters = None
    migration_summary = sm.migration_summary(conn)
    if migration_summary.get("parameters"):
        installed_parameters = migration_summary["parameters"]
    installed_version = migration_summary.get("version", "?")
    print(f"    installed version: {installed_version} → target: {target_version}")
    print(f"    parameters: {len(standard_params)} standard, {len(app_only_params)} app-only")

    upgrade_dlg = UpgradeDialog(
        pkg,
        standard_params,
        app_only_params,
        target_version,
        installed_parameters,
        dialog,
    )
    upgrade_dlg.show()
    _app.processEvents()

    _grab(upgrade_dlg, "08_upgrade_dialog.png")

    params = upgrade_dlg.parameters()
    beta_testing = upgrade_dlg.beta_testing()

    # Check if the installed version was beta testing (for force option)
    installed_beta_testing = migration_summary.get("beta_testing", False)

    options = {
        "beta_testing": beta_testing,
        "force": installed_beta_testing,
        **upgrade_dlg.roles_options(),
    }
    upgrade_dlg.close()
    return params, options


def step_09_upgrade_run(dialog: MainDialog, params: dict, options: dict):
    """Step 09 – Start the upgrade operation, screenshot progress, and wait for completion."""
    mw = _mod_widget(dialog)
    task = _operation_task(dialog)

    print("    starting upgrade operation...")
    mw._ModuleWidget__startOperation("upgrade", params, options)

    print("    capturing progress screenshot (2s delay)...")
    _process_events_for(2_000)

    upgrade_btn = mw.moduleInfo_upgrade_pushButton
    click_pos = _widget_center_in(upgrade_btn, dialog)
    _grab(dialog, "09_upgrade_in_progress.png", click_targets=[click_pos])

    print("    waiting for upgrade to complete...")
    _wait_for_signal(task.signalFinished, timeout_ms=300_000)
    _process_events_for(200)
    _close_message_boxes()
    _app.processEvents()
    print("    upgrade finished")


def step_10_roles_dialog(dialog: MainDialog):
    """Step 10 – Open the role management dialog and screenshot it."""
    _mod_widget(dialog)
    cfg = _pum_config(dialog)
    conn = _connection(dialog)
    if cfg is None:
        raise RuntimeError("PUM config not loaded for roles")

    role_manager = cfg.role_manager()
    print(f"    querying roles inventory ({len(role_manager.roles)} configured roles)...")
    result = role_manager.roles_inventory(connection=conn, include_superusers=True)
    print(
        f"    inventory: {len(result.configured_roles)} configured, {len(result.grantee_roles)} grantee, "
        f"{len(result.unknown_roles)} unknown, {len(result.other_login_roles)} login"
    )

    roles_dlg = RolesManageDialog(
        result,
        connection=conn,
        role_manager=role_manager,
        parent=dialog,
    )
    roles_dlg.show()
    _app.processEvents()

    _grab(roles_dlg, "10_roles_dialog.png")
    roles_dlg.close()


def step_11_uninstall(dialog: MainDialog):
    """Step 11 – Uninstall the module to leave the database clean (no screenshot)."""
    mw = _mod_widget(dialog)
    cfg = _pum_config(dialog)
    conn = _connection(dialog)
    task = _operation_task(dialog)
    if cfg is None:
        raise RuntimeError("PUM config not loaded for uninstall")

    from oqtopus.libs.pum.schema_migrations import SchemaMigrations

    sm = SchemaMigrations(cfg)
    if not sm.exists(conn):
        print("    nothing to uninstall — database already clean")
        return

    summary = sm.migration_summary(conn)
    version = summary.get("version", "?")
    params = summary.get("parameters") or {}
    print(f"    uninstalling version {version}...")

    mw._ModuleWidget__startOperation("uninstall", params, {})

    print("    waiting for uninstall to complete...")
    _wait_for_signal(task.signalFinished, timeout_ms=300_000)
    _process_events_for(200)
    _close_message_boxes()
    _app.processEvents()
    print("    uninstall finished — database clean")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def confirm_workflow():
    """Print a summary of the planned workflow and ask for confirmation.

    Called before opening any dialog or touching the database.
    Raises ``SystemExit`` if the user declines.
    """
    print()
    print("  Planned workflow")
    print("  ────────────────")
    print(f"  Service:  {PG_SERVICE}")
    print(f"  Module:   {MODULE_ID}")
    print(f"  Version:  {INSTALL_VERSION}")
    print(f"  Branch:   {DEV_BRANCH}")
    print(f"  Output:   {OUTPUT_DIR}")
    print()
    print("  Steps: connect → install → upgrade → roles → uninstall")
    print()
    answer = input("  Proceed? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        raise SystemExit(0)


def main():
    confirm_workflow()

    _ensure_output_dir()
    PluginUtils.init_logger()

    conf_path = Path("oqtopus/default_config.yaml")
    dialog = MainDialog(modules_config_path=conf_path)
    dialog.resize(900, 650)
    dialog.show()
    _app.processEvents()

    print("  01 Select PG service...")
    step_01_select_service(dialog)

    steps = [
        ("02 Select module", lambda: step_02_select_module(dialog)),
        ("03 Select version", lambda: step_03_select_version(dialog)),
    ]

    for label, fn in steps:
        print(f"  {label}...")
        fn()

    # Install workflow
    print("  04 Install dialog...")
    params, options = step_04_install_dialog(dialog)

    print("  05 Install (running)...")
    step_05_install_run(dialog, params, options)

    # Load dev branches and select one
    print("  06 Load development branches...")
    step_06_load_dev_branches(dialog)

    print("  07 Select dev branch...")
    step_07_select_dev_branch(dialog)

    # Upgrade workflow
    print("  08 Upgrade dialog...")
    params, options = step_08_upgrade_dialog(dialog)

    print("  09 Upgrade (running)...")
    step_09_upgrade_run(dialog, params, options)

    # Roles
    print("  10 Roles dialog...")
    step_10_roles_dialog(dialog)

    # Cleanup: uninstall the module so the database is left clean
    print("  11 Uninstall (cleanup)...")
    step_11_uninstall(dialog)

    dialog.close()
    print("Done — screenshots in", OUTPUT_DIR)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
