import os
import sys

import psycopg
from qgis.PyQt.QtCore import QRect, Qt, pyqtSignal
from qgis.PyQt.QtGui import QAction, QBrush, QColor, QFont, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (
    QDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ..libs.pgserviceparser import conf_path as pgserviceparser_conf_path
from ..libs.pgserviceparser import service_config as pgserviceparser_service_config
from ..libs.pgserviceparser import service_names as pgserviceparser_service_names
from ..libs.pgserviceparser.gui.message_bar import MessageBar
from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import QtUtils
from .database_baseline_dialog import DatabaseBaselineDialog
from .database_create_dialog import DatabaseCreateDialog
from .database_dump_dialog import DatabaseDumpDialog
from .database_duplicate_dialog import DatabaseDuplicateDialog
from .database_restore_dialog import DatabaseRestoreDialog

libs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "libs"))
if libs_path not in sys.path:
    sys.path.insert(0, libs_path)

from ..libs.pum.schema_migrations import SchemaMigrations  # noqa: E402

DIALOG_UI = PluginUtils.get_ui_class("database_connection_widget.ui")


class DatabaseConnectionWidget(QWidget, DIALOG_UI):

    signal_connectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)

        self.db_database_label.setText(self.tr("No database"))
        QtUtils.setForegroundColor(self.db_database_label, PluginUtils.COLOR_WARNING)
        QtUtils.setFontItalic(self.db_database_label, True)

        self.__loadDatabaseInformations()
        self.db_services_comboBox.currentIndexChanged.connect(self.__serviceChanged)

        db_operations_menu = QMenu(self.db_operations_toolButton)

        actionManagePgServices = QAction(self.tr("Manage PG services"), db_operations_menu)
        actionCreateDb = QAction(self.tr("Create database and service"), db_operations_menu)
        actionReloadPgServices = QAction(self.tr("Reload PG Service config"), db_operations_menu)

        actionManagePgServices.triggered.connect(self.__managePgServicesClicked)
        actionCreateDb.triggered.connect(self.__createDatabaseClicked)
        actionReloadPgServices.triggered.connect(self.__loadDatabaseInformations)

        db_operations_menu.addAction(actionManagePgServices)
        db_operations_menu.addSeparator()
        db_operations_menu.addAction(actionCreateDb)
        db_operations_menu.addSeparator()
        db_operations_menu.addAction(actionReloadPgServices)

        self.db_operations_toolButton.setMenu(db_operations_menu)

        # Service-specific operations menu (next to service combobox)
        service_menu = QMenu(self.db_service_toolButton)
        self.__actionCreateDbForService = QAction(self.tr("Create database"), service_menu)
        self.__actionDuplicateDb = QAction(self.tr("Duplicate database"), service_menu)
        self.__actionDropDb = QAction(self.tr("Drop database"), service_menu)

        self.__actionCreateDbForService.triggered.connect(self.__createDatabaseForServiceClicked)
        self.__actionDuplicateDb.triggered.connect(self.__duplicateDatabaseClicked)
        self.__actionDropDb.triggered.connect(self.__dropDatabaseClicked)

        self.__actionDumpDb = QAction(self.tr("Dump database"), service_menu)
        self.__actionRestoreDb = QAction(self.tr("Restore database"), service_menu)
        self.__actionSetBaseline = QAction(self.tr("Set baseline"), service_menu)

        self.__actionDumpDb.triggered.connect(self.__dumpDatabaseClicked)
        self.__actionRestoreDb.triggered.connect(self.__restoreDatabaseClicked)
        self.__actionSetBaseline.triggered.connect(self.__setBaselineClicked)

        service_menu.addAction(self.__actionCreateDbForService)
        service_menu.addAction(self.__actionDuplicateDb)
        service_menu.addAction(self.__actionDropDb)
        service_menu.addSeparator()
        service_menu.addAction(self.__actionDumpDb)
        service_menu.addAction(self.__actionRestoreDb)
        service_menu.addSeparator()
        service_menu.addAction(self.__actionSetBaseline)

        self.db_service_toolButton.setMenu(service_menu)

        self.__actionCreateDbForService.setDisabled(True)
        self.__actionDuplicateDb.setDisabled(True)
        self.__actionDropDb.setDisabled(True)
        self.__actionDumpDb.setDisabled(True)
        self.__actionRestoreDb.setDisabled(True)
        self.__actionSetBaseline.setDisabled(True)

        self.__database_connection = None
        self.__installed_module_ids = []
        self.__installed_module_versions: dict[str, str] = {}

        # Setup info icon (hidden by default) — white "i" in blue circle
        self.__db_info_pixmap = self.__createInfoPixmap(16)
        self.db_info_icon_label.setFixedSize(16, 16)
        self.db_info_icon_label.setPixmap(self.__db_info_pixmap)
        self.db_info_icon_label.setVisible(False)

        try:
            self.__serviceChanged()
        except Exception:
            # Silence errors during widget initialization
            pass

    def close(self):
        """Close the database connection."""
        self.__set_connection(None)

    def getConnection(self):
        """
        Returns the current database connection.
        If no connection is established, returns None.
        """
        return self.__database_connection

    def getService(self):
        """
        Returns the current service name.
        If no service is selected, returns None.
        """
        if self.db_services_comboBox.currentText() == "":
            return None
        return self.db_services_comboBox.currentText()

    def __loadDatabaseInformations(self):
        pg_service_conf_path = pgserviceparser_conf_path()
        QtUtils.setPathLinkWithEllipsis(
            self.db_servicesConfigFilePath_label, str(pg_service_conf_path.resolve())
        )

        self.db_services_comboBox.clear()

        try:
            self.db_services_comboBox.addItem(self.tr("Please select a service"), None)
            # Disable the placeholder item
            model = self.db_services_comboBox.model()
            item = model.item(0)
            item.setEnabled(False)

            for service_name in pgserviceparser_service_names():
                self.db_services_comboBox.addItem(service_name, service_name)
        except Exception as exception:
            MessageBar.pushErrorToBar(self, self.tr("Can't load database services:"), exception)
            return

    def __serviceChanged(self, index=None):
        # Check if placeholder is selected (currentData is None)
        if self.db_services_comboBox.currentData() is None:
            self.db_database_label.setText(self.tr("No database"))
            QtUtils.setForegroundColor(self.db_database_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.db_database_label, True)

            self.__actionCreateDbForService.setDisabled(True)
            self.__actionDuplicateDb.setDisabled(True)
            self.__actionDropDb.setDisabled(True)
            self.__actionDumpDb.setDisabled(True)
            self.__actionRestoreDb.setDisabled(True)
            self.__actionSetBaseline.setDisabled(True)

            self.db_info_icon_label.setVisible(False)
            self.__set_connection(None)
            return

        service_name = self.db_services_comboBox.currentText()
        service_config = pgserviceparser_service_config(service_name)

        service_database = service_config.get("dbname", None)

        if service_database is None:
            self.db_database_label.setText(self.tr("No database provided by the service"))
            QtUtils.setForegroundColor(self.db_database_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.db_database_label, True)

            self.__actionCreateDbForService.setEnabled(True)
            self.__actionDuplicateDb.setDisabled(True)
            self.__actionDropDb.setDisabled(True)
            self.__actionDumpDb.setDisabled(True)
            self.__actionRestoreDb.setDisabled(True)
            self.__actionSetBaseline.setDisabled(True)
            self.db_info_icon_label.setVisible(False)
            return

        self.db_database_label.setText(service_database)
        QtUtils.resetForegroundColor(self.db_database_label)
        QtUtils.setFontItalic(self.db_database_label, False)

        # Try connection
        try:
            database_connection = psycopg.connect(service=service_name)
            self.__set_connection(database_connection)

        except Exception as exception:
            self.__set_connection(None)

            self.__actionCreateDbForService.setEnabled(True)
            self.__actionDuplicateDb.setDisabled(True)
            self.__actionDropDb.setDisabled(True)
            self.__actionDumpDb.setDisabled(True)
            self.__actionRestoreDb.setDisabled(True)
            self.__actionSetBaseline.setDisabled(True)
            self.db_moduleInfo_label.setText("Can't connect to service.")
            QtUtils.setForegroundColor(self.db_moduleInfo_label, PluginUtils.COLOR_WARNING)
            self.db_info_icon_label.setVisible(False)
            errorText = self.tr(f"Can't connect to service '{service_name}':\n{exception}.")
            logger.error(errorText)
            return

        self.__actionCreateDbForService.setDisabled(True)
        self.__actionDuplicateDb.setEnabled(True)
        self.__actionDropDb.setEnabled(True)
        self.__actionDumpDb.setEnabled(True)
        self.__actionRestoreDb.setEnabled(True)
        self.__actionSetBaseline.setEnabled(True)

        self.db_moduleInfo_label.setText("Connected.")
        logger.info(f"Connected to service '{service_name}'.")
        QtUtils.resetForegroundColor(self.db_moduleInfo_label)

        self.__updateDatabaseInfoTooltip()

        self.refreshInstalledModules()

    def __updateDatabaseInfoTooltip(self):
        """Query PG version and installed extensions, show info icon with tooltip."""
        if self.__database_connection is None:
            self.db_info_icon_label.setVisible(False)
            self.db_moduleInfo_label.setToolTip("")
            return

        tooltip_lines = []
        try:
            with self.__database_connection.cursor() as cur:
                cur.execute("SELECT version()")
                pg_version = cur.fetchone()[0]
                tooltip_lines.append(f"<b>PostgreSQL:</b> {pg_version}")

                cur.execute(
                    "SELECT name, default_version, installed_version "
                    "FROM pg_available_extensions "
                    "WHERE installed_version IS NOT NULL "
                    "ORDER BY name"
                )
                extensions = cur.fetchall()
                if extensions:
                    tooltip_lines.append("<br><b>Installed extensions:</b>")
                    for name, default_version, installed_version in extensions:
                        tooltip_lines.append(f"&nbsp;&nbsp;\u2022 {name} ({installed_version})")
        except Exception as e:
            logger.warning(f"Could not retrieve database info: {e}")
            self.db_info_icon_label.setVisible(False)
            return

        tooltip_html = "<p style='font-size:11pt'>" + "<br>".join(tooltip_lines) + "</p>"
        self.db_info_icon_label.setToolTip(tooltip_html)
        self.db_moduleInfo_label.setToolTip(tooltip_html)
        self.db_info_icon_label.setVisible(True)

    @staticmethod
    def __createInfoPixmap(size: int) -> QPixmap:
        """Return a *size*×*size* pixmap with a white 'i' inside a blue circle."""
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))  # transparent background

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Blue circle
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(30, 115, 190)))
        painter.drawEllipse(0, 0, size, size)

        # White "i"
        painter.setPen(QColor(255, 255, 255))
        font = QFont()
        font.setPixelSize(int(size * 0.7))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "i")

        painter.end()
        return pixmap

    def __managePgServicesClicked(self):
        from ..libs.pgserviceparser.gui.service_widget import PGServiceParserWidget

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Manage PG services"))
        dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout(dialog)
        service_widget = PGServiceParserWidget(parent=dialog)
        layout.addWidget(service_widget)
        dialog.exec()

        self.__loadDatabaseInformations()

    def __createDatabaseClicked(self):
        databaseCreateDialog = DatabaseCreateDialog(
            selected_service=self.db_services_comboBox.currentText(), parent=self
        )

        if databaseCreateDialog.exec() == QDialog.DialogCode.Rejected:
            return

        self.__loadDatabaseInformations()

        # Select the created service
        created_service_name = databaseCreateDialog.created_service_name()
        self.db_services_comboBox.setCurrentText(created_service_name)

        MessageBar.pushSuccessToBar(
            self, self.tr(f"Database and service '{created_service_name}' created successfully.")
        )

    def __duplicateDatabaseClicked(self):
        databaseDuplicateDialog = DatabaseDuplicateDialog(
            selected_service=self.db_services_comboBox.currentText(), parent=self
        )

        # Close the current connection otherwise it will block the database duplication
        if self.__database_connection is not None:
            self.__database_connection.close()
            self.__database_connection = None

        if databaseDuplicateDialog.exec() == QDialog.DialogCode.Rejected:
            self.__serviceChanged()
            return

        self.__loadDatabaseInformations()

        created_service_name = databaseDuplicateDialog.created_service_name()
        self.db_services_comboBox.setCurrentText(created_service_name)

        MessageBar.pushSuccessToBar(
            self, self.tr(f"Database duplicated to service '{created_service_name}'.")
        )

    def getInstalledModuleIds(self) -> list[str]:
        """Return the list of module IDs currently installed in the database."""
        return self.__installed_module_ids

    def getInstalledModuleVersion(self, module_id: str) -> str | None:
        """Return the installed version for *module_id*, or None."""
        return self.__installed_module_versions.get(module_id)

    def refreshInstalledModules(self):
        """Refresh the installed modules list in the groupbox."""
        # Clear existing labels
        layout = self.installed_modules_groupbox.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.__installed_module_ids = []
        self.__installed_module_versions = {}

        if self.__database_connection is None:
            self.installed_modules_groupbox.setVisible(False)
            return

        try:
            migration_details = SchemaMigrations.schemas_with_migration_details(
                self.__database_connection
            )
        except Exception:
            self.installed_modules_groupbox.setVisible(False)
            return

        if not migration_details:
            label = QLabel(self.tr("No modules installed"))
            layout.addWidget(label)
            self.installed_modules_groupbox.setVisible(True)
            return

        self.__installed_module_ids = [
            info["module"] for info in migration_details if info["module"]
        ]
        self.__installed_module_versions = {
            info["module"]: info["version"]
            for info in migration_details
            if info["module"] and info["version"]
        }

        for info in migration_details:
            module_label = info["module"] or info["schema"]
            schema = info["schema"]
            version = info["version"] or "?"

            # Build display text
            beta_text = " \u26a0\ufe0f" if info["beta_testing"] else ""
            display = f"\u2022 <b>{module_label}</b> ({version}){beta_text}"

            # Build tooltip with details (rich HTML for bigger text)
            tooltip_lines = []
            tooltip_lines.append(f"<b>Module:</b> {module_label}")
            tooltip_lines.append(f"<b>Schema:</b> {schema}")
            tooltip_lines.append(f"<b>Version:</b> {version}")
            if info["beta_testing"]:
                tooltip_lines.append("\u26a0\ufe0f <b>Beta testing</b>")
            if info["installed_date"]:
                tooltip_lines.append(
                    f"<b>Installed:</b> {info['installed_date'].strftime('%Y-%m-%d %H:%M')}"
                )
            if info["upgrade_date"]:
                tooltip_lines.append(
                    f"<b>Last upgrade:</b> {info['upgrade_date'].strftime('%Y-%m-%d %H:%M')}"
                )
            if info.get("parameters") and isinstance(info["parameters"], dict):
                tooltip_lines.append("<br><b>Parameters:</b>")
                for param_name, param_value in info["parameters"].items():
                    tooltip_lines.append(f"&nbsp;&nbsp;{param_name} = {param_value}")

            tooltip_html = "<p style='font-size:11pt'>" + "<br>".join(tooltip_lines) + "</p>"
            label = QLabel(display)
            label.setToolTip(tooltip_html)
            layout.addWidget(label)

        self.installed_modules_groupbox.setVisible(True)

    def __createDatabaseForServiceClicked(self):
        service_name = self.db_services_comboBox.currentText()
        if not service_name or self.db_services_comboBox.currentData() is None:
            return

        databaseCreateDialog = DatabaseCreateDialog(
            selected_service=service_name,
            fixed_service_name=service_name,
            parent=self,
        )

        if databaseCreateDialog.exec() == QDialog.DialogCode.Rejected:
            return

        self.__loadDatabaseInformations()
        self.db_services_comboBox.setCurrentText(service_name)

        MessageBar.pushSuccessToBar(
            self, self.tr(f"Database created for service '{service_name}'.")
        )

    def __dropDatabaseClicked(self):
        service_name = self.db_services_comboBox.currentText()
        if not service_name or self.db_services_comboBox.currentData() is None:
            return

        service_config = pgserviceparser_service_config(service_name)
        db_name = service_config.get("dbname")
        if not db_name:
            MessageBar.pushWarningToBar(
                self, self.tr("No database name configured for this service.")
            )
            return

        reply = QMessageBox.warning(
            self,
            self.tr("Drop database"),
            self.tr(
                f"Are you sure you want to drop the database '{db_name}'?\n\n"
                "This action cannot be undone!"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Close existing connection (cannot drop while connected)
        self.__set_connection(None)

        try:
            from ..libs.pum.database import drop_database

            drop_database({"service": service_name, "dbname": "postgres"}, db_name)

            MessageBar.pushSuccessToBar(self, self.tr(f"Database '{db_name}' has been dropped."))
        except Exception as e:
            MessageBar.pushErrorToBar(self, self.tr(f"Failed to drop database: {e}"))

        self.__serviceChanged()

    def __setBaselineClicked(self):
        if self.__database_connection is None:
            return

        dialog = DatabaseBaselineDialog(
            connection=self.__database_connection,
            parent=self,
        )

        if dialog.exec() == QDialog.DialogCode.Rejected:
            return

        self.__serviceChanged()
        MessageBar.pushSuccessToBar(self, self.tr("Baseline set successfully."))

    def __dumpDatabaseClicked(self):
        service_name = self.db_services_comboBox.currentText()
        if not service_name or self.db_services_comboBox.currentData() is None:
            return

        dialog = DatabaseDumpDialog(
            service_name=service_name,
            parent=self,
        )

        if dialog.exec() == QDialog.DialogCode.Rejected:
            return

        MessageBar.pushSuccessToBar(self, self.tr("Database dumped successfully."))

    def __restoreDatabaseClicked(self):
        service_name = self.db_services_comboBox.currentText()
        if not service_name or self.db_services_comboBox.currentData() is None:
            return

        dialog = DatabaseRestoreDialog(
            service_name=service_name,
            parent=self,
        )

        if dialog.exec() == QDialog.DialogCode.Rejected:
            return

        self.__serviceChanged()
        MessageBar.pushSuccessToBar(self, self.tr("Database restored successfully."))

    def __set_connection(self, connection):
        """
        Set the current database connection and emit the signal_connectionChanged signal.
        Closes the previous connection if it exists.
        """
        if self.__database_connection is not None:
            try:
                self.__database_connection.close()
            except Exception:
                pass
        self.__database_connection = connection
        self.refreshInstalledModules()
        self.signal_connectionChanged.emit()
