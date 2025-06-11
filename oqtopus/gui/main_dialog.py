# -----------------------------------------------------------
#
# Profile
# Copyright (C) 2025  Damiano Lombardi
# -----------------------------------------------------------
#
# licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, print to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# ---------------------------------------------------------------------


import logging
import os
import shutil
import sys

import psycopg
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QAction, QColor, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMenu,
    QMenuBar,
    QMessageBox,
    QStyle,
    QTreeWidgetItem,
)

from ..core.module import Module
from ..core.module_version import ModuleVersion
from ..core.package_prepare_task import PackagePrepareTask
from ..utils.plugin_utils import LoggingBridge, PluginUtils, logger
from ..utils.qt_utils import CriticalMessageBox, OverrideCursor, QtUtils
from .about_dialog import AboutDialog
from .settings_dialog import SettingsDialog

libs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "libs"))
if libs_path not in sys.path:
    sys.path.insert(0, libs_path)

from pgserviceparser import conf_path as pgserviceparser_conf_path  # noqa: E402
from pgserviceparser import (  # noqa: E402
    service_config as pgserviceparser_service_config,
)
from pgserviceparser import service_names as pgserviceparser_service_names  # noqa: E402
from pum.pum_config import PumConfig  # noqa: E402
from pum.schema_migrations import SchemaMigrations  # noqa: E402
from pum.upgrader import Upgrader  # noqa: E402

from .database_create_dialog import DatabaseCreateDialog  # noqa: E402
from .database_duplicate_dialog import DatabaseDuplicateDialog  # noqa: E402

DIALOG_UI = PluginUtils.get_ui_class("main_dialog.ui")


class MainDialog(QDialog, DIALOG_UI):

    MODULE_VERSION_SPECIAL_LOAD_DEVELOPMENT = "Load development versions"

    COLOR_GREEN = QColor(12, 167, 137)
    COLOR_WARNING = QColor(255, 165, 0)

    def __init__(self, modules_config, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        self.loggingBridge = LoggingBridge(
            level=logging.NOTSET, excluded_modules=["urllib3.connectionpool"]
        )
        self.loggingBridge.loggedLine.connect(self.__logged_line)
        logging.getLogger().addHandler(self.loggingBridge)

        self.buttonBox.rejected.connect(self.__closeDialog)
        self.buttonBox.helpRequested.connect(self.__helpRequested)

        self.__modules_config = modules_config
        self.__current_module = None

        self.__database_connection = None

        self.__data_model_dir = None
        self.__pum_config = None
        self.__project_file = None

        # Init GUI Modules
        self.__initGuiModules()

        # Init GUI Database
        self.__initGuiDatabase()

        # Init GUI Module Info
        self.__initGuiModuleInfo()

        # Init GUI Project
        self.__initGuiProject()

        # Init GUI Logs
        self.__initGuiLogs()

        self.__packagePrepareTask = PackagePrepareTask(self)
        self.__packagePrepareTask.finished.connect(self.__packagePrepareTaskFinished)
        self.__packagePrepareTask.signalPackagingProgress.connect(
            self.__packagePrepareTaskProgress
        )

        # Add menubar
        self.menubar = QMenuBar(self)
        # On macOS, setNativeMenuBar(False) to show the menu bar inside the dialog window
        if sys.platform == "darwin":
            self.menubar.setNativeMenuBar(False)
        self.layout().setMenuBar(self.menubar)

        # Settings action
        settings_action = QAction(self.tr("Settings"), self)
        settings_action.triggered.connect(self.__open_settings_dialog)

        # About action
        about_action = QAction(self.tr("About"), self)
        about_action.triggered.connect(self.__show_about_dialog)

        # Add actions to menubar
        self.menubar.addAction(settings_action)
        self.menubar.addAction(about_action)

        logger.info("Ready.")

    def __initGuiModules(self):
        self.module_module_comboBox.clear()
        self.module_module_comboBox.addItem(self.tr("Please select a module"), None)
        for config_module in self.__modules_config.modules:
            module = Module(
                config_module.name, config_module.organisation, config_module.repository
            )
            self.module_module_comboBox.addItem(module.name, module)

        self.module_latestVersion_label.setText("")
        QtUtils.setForegroundColor(self.module_latestVersion_label, self.COLOR_GREEN)

        self.module_version_comboBox.clear()
        self.module_version_comboBox.addItem(self.tr("Please select a version"), None)

        self.module_zipPackage_groupBox.setVisible(False)

        self.module_module_comboBox.currentIndexChanged.connect(self.__moduleChanged)
        self.module_version_comboBox.currentIndexChanged.connect(self.__moduleVersionChanged)
        self.module_seeChangeLog_pushButton.clicked.connect(self.__seeChangeLogClicked)
        self.module_browseZip_toolButton.clicked.connect(self.__moduleBrowseZipClicked)

    def __initGuiDatabase(self):
        self.db_database_label.setText(self.tr("No database"))
        QtUtils.setForegroundColor(self.db_database_label, self.COLOR_WARNING)
        QtUtils.setFontItalic(self.db_database_label, True)

        self.__loadDatabaseInformations()
        self.db_services_comboBox.currentIndexChanged.connect(self.__serviceChanged)

        db_operations_menu = QMenu(self.db_operations_toolButton)

        actionCreateDb = QAction(self.tr("Create database"), db_operations_menu)
        self.__actionDuplicateDb = QAction(self.tr("Duplicate database"), db_operations_menu)

        actionCreateDb.triggered.connect(self.__createDatabaseClicked)
        self.__actionDuplicateDb.triggered.connect(self.__duplicateDatabaseClicked)

        db_operations_menu.addAction(actionCreateDb)
        db_operations_menu.addAction(self.__actionDuplicateDb)

        self.db_operations_toolButton.setMenu(db_operations_menu)

        try:
            self.__serviceChanged()
        except Exception:
            # Silence errors during dialog initialization
            pass

    def __initGuiModuleInfo(self):
        QtUtils.setForegroundColor(self.moduleInfo_NoModuleFound_label, self.COLOR_WARNING)
        QtUtils.setFontItalic(self.moduleInfo_NoModuleFound_label, True)

        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageInstall)

        self.moduleInfo_install_pushButton.clicked.connect(self.__installModuleClicked)
        self.moduleInfo_upgrade_pushButton.clicked.connect(self.__upgradeModuleClicked)

    def __initGuiProject(self):
        self.project_install_pushButton.clicked.connect(self.__projectInstallClicked)
        self.project_seeChangelog_pushButton.clicked.connect(self.__projectSeeChangelogClicked)

    def __initGuiLogs(self):
        self.logs_openFile_toolButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        )
        self.logs_openFolder_toolButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self.logs_clear_toolButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton)
        )

        self.logs_openFile_toolButton.clicked.connect(self.__logsOpenFileClicked)
        self.logs_openFolder_toolButton.clicked.connect(self.__logsOpenFolderClicked)
        self.logs_clear_toolButton.clicked.connect(self.__logsClearClicked)

    def __logged_line(self, record, line):

        treeWidgetItem = QTreeWidgetItem([record.levelname, record.name, record.msg])

        self.logs_treeWidget.addTopLevelItem(treeWidgetItem)

        # Automatically scroll to the bottom of the logs
        scroll_bar = self.logs_treeWidget.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def __closeDialog(self):
        if self.__packagePrepareTask.isRunning():
            self.__packagePrepareTask.cancel()
            self.__packagePrepareTask.wait()

        self.accept()

    def __helpRequested(self):
        help_page = "https://github.com/oqtopus/Oqtopus"
        logger.info(f"Opening help page {help_page}")
        QDesktopServices.openUrl(QUrl(help_page))

    def __loadDatabaseInformations(self):
        self.db_servicesConfigFilePath_label.setText(pgserviceparser_conf_path().as_posix())

        self.db_services_comboBox.clear()

        try:
            for service_name in pgserviceparser_service_names():
                self.db_services_comboBox.addItem(service_name)
        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't load database services:"), exception, self
            ).exec()
            return

    def __moduleChanged(self, index):
        if self.module_module_comboBox.currentData() == self.__current_module:
            return

        self.__current_module = self.module_module_comboBox.currentData()

        self.module_latestVersion_label.setText("")
        self.module_version_comboBox.clear()
        self.module_version_comboBox.addItem(self.tr("Please select a version"), None)

        if self.__current_module is None:
            return

        try:
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                if self.__current_module.versions == list():
                    self.__current_module.load_versions()

                for module_version in self.__current_module.versions:
                    self.module_version_comboBox.addItem(
                        module_version.display_name(), module_version
                    )

                if self.__current_module.latest_version is not None:
                    self.module_latestVersion_label.setText(
                        f"Latest: {self.__current_module.latest_version.name}"
                    )

        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't load module versions:"), exception, self
            ).exec()
            return

        self.module_version_comboBox.insertSeparator(self.module_version_comboBox.count())
        self.module_version_comboBox.addItem(
            self.tr("Load from ZIP file"),
            ModuleVersion(
                organisation=self.__current_module.organisation,
                repository=self.__current_module.repository,
                json_payload=None,
                type=ModuleVersion.Type.FROM_ZIP,
            ),
        )

        self.module_version_comboBox.insertSeparator(self.module_version_comboBox.count())
        self.module_version_comboBox.addItem(
            self.tr("Load additional branches"), self.MODULE_VERSION_SPECIAL_LOAD_DEVELOPMENT
        )

        logger.info(f"Versions loaded for module '{self.__current_module.name}'.")

    def __moduleVersionChanged(self, index):

        if (
            self.module_version_comboBox.currentData()
            == self.MODULE_VERSION_SPECIAL_LOAD_DEVELOPMENT
        ):
            self.__loadDevelopmentVersions()
            return

        current_module_version = self.module_version_comboBox.currentData()
        if current_module_version is None:
            return

        if current_module_version.type == current_module_version.Type.FROM_ZIP:
            self.module_zippackage_groupBox.setVisible(True)
            return
        else:
            self.module_zipPackage_groupBox.setVisible(False)

        self.__data_model_dir = None
        self.__pum_config = None
        self.__project_file = None

        loading_text = self.tr(
            f"Loading packages for module '{self.module_module_comboBox.currentText()}' version '{current_module_version.display_name()}'..."
        )
        self.module_information_label.setText(loading_text)
        QtUtils.resetForegroundColor(self.module_information_label)
        logger.info(loading_text)

        self.module_informationDatamodel_label.setText("-")
        self.module_informationProject_label.setText("-")
        self.module_informationPlugin_label.setText("-")

        if self.__packagePrepareTask.isRunning():
            self.__packagePrepareTask.cancel()
            self.__packagePrepareTask.wait()

        self.__packagePrepareTask.startFromModuleVersion(current_module_version)

    def __loadDevelopmentVersions(self):
        if self.__current_module is None:
            return

        with OverrideCursor(Qt.CursorShape.WaitCursor):
            self.__current_module.load_development_versions()

        if self.__current_module.development_versions == list():
            QMessageBox.warning(
                self,
                self.tr("No development versions found"),
                self.tr("No development versions found for this module."),
            )
            return

        self.module_version_comboBox.removeItem(self.module_version_comboBox.count() - 1)

        for module_version in self.__current_module.development_versions:
            self.module_version_comboBox.addItem(module_version.display_name(), module_version)

    def __moduleBrowseZipClicked(self):
        filename, format = QFileDialog.getOpenFileName(
            self, self.tr("Open from zip"), None, self.tr("Zip package (*.zip)")
        )

        if filename == "":
            return

        self.module_fromZip_lineEdit.setText(filename)

        try:
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                self.__loadModuleFromZip(filename)
        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't load module from zip file:"), exception, self
            ).exec()
            return

    def __loadModuleFromZip(self, filename):

        self.__data_model_dir = None
        self.__pum_config = None
        self.__project_file = None

        if self.__packagePrepareTask.isRunning():
            self.__packagePrepareTask.cancel()
            self.__packagePrepareTask.wait()

        self.__packagePrepareTask.startFromZip(filename)

    def __packagePrepareTaskFinished(self):
        logger.info("Load package task finished")

        if self.__packagePrepareTask.lastError is not None:
            error_text = self.tr("Can't load module package:")
            CriticalMessageBox(
                self.tr("Error"), error_text, self.__packagePrepareTask.lastError, self
            ).exec()
            self.module_information_label.setText(error_text)
            QtUtils.setForegroundColor(self.module_information_label, self.COLOR_WARNING)
            return

        package_dir = self.module_version_comboBox.currentData().package_dir
        logger.info(f"Package loaded into '{package_dir}'")
        self.module_information_label.setText(package_dir)
        QtUtils.resetForegroundColor(self.module_information_label)

        asset_datamodel = self.module_version_comboBox.currentData().asset_datamodel
        if asset_datamodel:
            self.module_informationDatamodel_label.setText(asset_datamodel.package_dir)
        else:
            self.module_informationDatamodel_label.setText("No asset available")

        asset_project = self.module_version_comboBox.currentData().asset_project
        if asset_project:
            self.module_informationProject_label.setText(asset_project.package_dir)
        else:
            self.module_informationProject_label.setText("No asset available")

        asset_plugin = self.module_version_comboBox.currentData().asset_plugin
        if asset_plugin:
            self.module_informationPlugin_label.setText(asset_plugin.package_dir)
        else:
            self.module_informationPlugin_label.setText("No asset available")

        self.__packagePrepareGetPUMConfig()
        self.__packagePrepareGetProjectFilename()

    def __packagePrepareGetPUMConfig(self):
        package_dir = self.module_version_comboBox.currentData().package_dir
        self.__data_model_dir = os.path.join(package_dir, "datamodel")
        pumConfigFilename = os.path.join(self.__data_model_dir, ".pum.yaml")
        if not os.path.exists(pumConfigFilename):
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(
                    f"The selected file '{self.__packagePrepareTask.zip_file}' does not contain a valid .pum.yaml file."
                ),
                None,
                self,
            ).exec()
            return

        try:
            self.__pum_config = PumConfig.from_yaml(pumConfigFilename, install_dependencies=True)
        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(f"Can't load PUM config from '{pumConfigFilename}':"),
                exception,
                self,
            ).exec()
            return

        logger.info(f"PUM config loaded from '{pumConfigFilename}'")

        self.parameters_groupbox.setParameters(self.__pum_config.parameters())

        self.db_parameter_demoData_comboBox.clear()
        self.db_parameter_demoData_comboBox.addItem(self.tr("Don't install demo data"), None)

        for demo_data_name, demo_data_file in self.__pum_config.demo_data().items():
            self.db_parameter_demoData_comboBox.addItem(demo_data_name, demo_data_file)

        sm = SchemaMigrations(self.__pum_config)
        migrationVersion = "0.0.0"
        if not self.__database_connection:
            self.db_moduleInfo_label.setText(self.tr("No database connection available"))
            QtUtils.setForegroundColor(self.db_moduleInfo_label, self.COLOR_WARNING)
        elif sm.exists(self.__database_connection):
            baseline_version = sm.baseline(self.__database_connection)
            self.db_moduleInfo_label.setText(self.tr(f"Version {baseline_version} found"))
            QtUtils.resetForegroundColor(self.db_moduleInfo_label)
            self.moduleInfo_upgrade_pushButton.setText(self.tr(f"Upgrade to {migrationVersion}"))

            self.moduleInfo_stackedWidget.setCurrentWidget(
                self.moduleInfo_stackedWidget_pageUpgrade
            )
        else:
            self.db_moduleInfo_label.setText(self.tr("No module found"))
            QtUtils.resetForegroundColor(self.db_moduleInfo_label)
            self.moduleInfo_install_pushButton.setText(self.tr(f"Install {migrationVersion}"))
            self.moduleInfo_stackedWidget.setCurrentWidget(
                self.moduleInfo_stackedWidget_pageInstall
            )

    def __packagePrepareGetProjectFilename(self):

        asset_project = self.module_version_comboBox.currentData().asset_project
        if asset_project is None:
            self.project_info_label.setText(
                self.tr("No project asset available for this module version.")
            )
            QtUtils.setForegroundColor(self.project_info_label, self.COLOR_WARNING)
            QtUtils.setFontItalic(self.db_database_label, True)
            return

        # Search for QGIS project file in self.__package_dir
        project_file_dir = os.path.join(asset_project.package_dir, "project")

        # Check if the directory exists
        if not os.path.exists(project_file_dir):
            self.project_info_label.setText(
                self.tr(f"Project directory '{project_file_dir}' does not exist.")
            )
            QtUtils.setForegroundColor(self.project_info_label, self.COLOR_WARNING)
            QtUtils.setFontItalic(self.db_database_label, True)
            return

        self.__project_file = None
        for root, dirs, files in os.walk(project_file_dir):
            for file in files:
                if file.endswith(".qgz") or file.endswith(".qgs"):
                    self.__project_file = os.path.join(root, file)
                    break

            if self.__project_file:
                break

        if self.__project_file is None:
            self.project_info_label.setText(
                self.tr(f"No QGIS project file (.qgz or .qgs) found into {project_file_dir}."),
            )
            QtUtils.setForegroundColor(self.project_info_label, self.COLOR_WARNING)
            QtUtils.setFontItalic(self.db_database_label, True)
            return

        self.project_info_label.setText(
            self.tr(self.__project_file),
        )
        QtUtils.setForegroundColor(self.project_info_label, self.COLOR_GREEN)
        QtUtils.setFontItalic(self.db_database_label, False)

    def __packagePrepareTaskProgress(self, progress):
        loading_text = self.tr("Load package task running...")
        logger.info(loading_text)
        self.module_information_label.setText(loading_text)

    def __seeChangeLogClicked(self):
        current_module_version = self.module_version_comboBox.currentData()

        if current_module_version == self.MODULE_VERSION_SPECIAL_LOAD_FROM_ZIP:
            QMessageBox.warning(
                self,
                self.tr("Can't open changelog"),
                self.tr("Changelog is not available for Zip packages."),
            )
            return

        if current_module_version is None:
            QMessageBox.warning(
                self,
                self.tr("Can't open changelog"),
                self.tr("Please select a module and version first."),
            )
            return

        if current_module_version.html_url is None:
            QMessageBox.warning(
                self,
                self.tr("Can't open changelog"),
                self.tr(f"Changelog not available for version '{current_module_version.name}'."),
            )
            return

        changelog_url = current_module_version.html_url
        logger.info(f"Opening changelog URL: {changelog_url}")
        QDesktopServices.openUrl(QUrl(changelog_url))

    def __serviceChanged(self, index=None):
        if self.db_services_comboBox.currentText() == "":
            self.db_database_label.setText(self.tr("No database"))
            QtUtils.setForegroundColor(self.db_database_label, self.COLOR_WARNING)
            QtUtils.setFontItalic(self.db_database_label, True)

            self.__actionDuplicateDb.setDisabled(True)
            return

        service_name = self.db_services_comboBox.currentText()
        service_config = pgserviceparser_service_config(service_name)

        service_database = service_config.get("dbname", None)

        if service_database is None:
            self.db_database_label.setText(self.tr("No database provided by the service"))
            QtUtils.setForegroundColor(self.db_database_label, self.COLOR_WARNING)
            QtUtils.setFontItalic(self.db_database_label, True)

            self.__actionDuplicateDb.setDisabled(True)
            return

        self.db_database_label.setText(service_database)
        QtUtils.resetForegroundColor(self.db_database_label)
        QtUtils.setFontItalic(self.db_database_label, False)

        self.__actionDuplicateDb.setEnabled(True)

        # Try connection
        try:
            self.__database_connection = psycopg.connect(service=service_name)

        except Exception as exception:
            self.__database_connection = None

            self.db_moduleInfo_label.setText("Can't connect to service.")
            QtUtils.setForegroundColor(self.db_moduleInfo_label, self.COLOR_WARNING)
            errorText = self.tr(f"Can't connect to service '{service_name}':\n{exception}.")
            logger.error(errorText)
            return

        self.db_moduleInfo_label.setText("Connected.")
        logger.info(f"Connected to service '{service_name}'.")
        QtUtils.resetForegroundColor(self.db_moduleInfo_label)

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

    def __duplicateDatabaseClicked(self):
        databaseDuplicateDialog = DatabaseDuplicateDialog(
            selected_service=self.db_services_comboBox.currentText(), parent=self
        )
        if databaseDuplicateDialog.exec() == QDialog.DialogCode.Rejected:
            return

    def __installModuleClicked(self):

        if self.__current_module is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please select a module first."), None, self
            ).exec()
            return

        current_module_version = self.module_version_comboBox.currentData()
        if current_module_version is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please select a module version first."), None, self
            ).exec()
            return

        if self.__database_connection is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please select a database service first."), None, self
            ).exec()
            return

        if self.__pum_config is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("No valid module available."), None, self
            ).exec()
            return

        parameters = self.parameters_groupbox.parameters_values()
        demo_data_name = self.db_parameter_demoData_comboBox.currentText()

        try:
            self.db_services_comboBox.currentText()
            upgrader = Upgrader(
                config=self.__pum_config,
            )
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                upgrader.install(
                    parameters=parameters,
                    connection=self.__database_connection,
                    roles=self.db_parameters_CreateAndGrantRoles_checkBox.isChecked(),
                    grant=self.db_parameters_CreateAndGrantRoles_checkBox.isChecked(),
                    demo_data=demo_data_name,
                )
        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't install the module:"), exception, self
            ).exec()
            return

    def __upgradeModuleClicked(self):
        if self.__current_module is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please select a module first."), None, self
            ).exec()
            return

        current_module_version = self.module_version_comboBox.currentData()
        if current_module_version is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please select a module version first."), None, self
            ).exec()
            return

        if self.__database_connection is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please select a database service first."), None, self
            ).exec()
            return

        if self.__pum_config is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("No valid module available."), None, self
            ).exec()
            return

        raise NotImplementedError("Upgrade module is not implemented yet")

    def __projectInstallClicked(self):

        if self.__current_module is None:
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("Please select a module and version first."),
            )
            return

        if self.module_version_comboBox.currentData() is None:
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("Please select a module version first."),
            )
            return

        asset_project = self.module_version_comboBox.currentData().asset_project
        if asset_project is None:
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("No project asset available for this module version."),
            )
            return

        package_dir = asset_project.package_dir
        if package_dir is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("No valid package directory available."), None, self
            ).exec()
            return

        # Search for QGIS project file in package_dir
        project_file_dir = os.path.join(package_dir, "project")

        # Check if the directory exists
        if not os.path.exists(project_file_dir):
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(f"Project directory '{project_file_dir}' does not exist."),
                None,
                self,
            ).exec()
            return

        self.__project_file = None
        for root, dirs, files in os.walk(project_file_dir):
            print(f"Searching for QGIS project file in {root}: {files}")
            for file in files:
                if file.endswith(".qgz") or file.endswith(".qgs"):
                    self.__project_file = os.path.join(root, file)
                    break

            if self.__project_file:
                break

        if self.__project_file is None:
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(f"No QGIS project file (.qgz or .qgs) found into {project_file_dir}."),
                None,
                self,
            ).exec()
            return

        install_destination = QFileDialog.getExistingDirectory(
            self,
            self.tr("Select installation directory"),
            "",
            QFileDialog.Option.ShowDirsOnly,
        )

        if not install_destination:
            return

        # Copy the project file to the selected directory
        try:
            shutil.copy(self.__project_file, install_destination)
            QMessageBox.information(
                self,
                self.tr("Project installed"),
                self.tr(
                    f"Project file '{self.__project_file}' has been copied to '{install_destination}'."
                ),
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Failed to copy project file: {e}"),
            )
            return

    def __projectSeeChangelogClicked(self):
        self.__seeChangeLogClicked()

    def __logsOpenFileClicked(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(PluginUtils.plugin_temp_path()))

    def __logsOpenFolderClicked(self):
        PluginUtils.open_logs_folder()

    def __logsClearClicked(self):
        self.logs_treeWidget.clear()

    def __open_settings_dialog(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def __show_about_dialog(self):
        dialog = AboutDialog(self)
        dialog.exec()
