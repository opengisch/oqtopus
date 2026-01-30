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


import os
import shutil
import sys

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QAction, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog,
    QMenuBar,
    QMessageBox,
)

from ..core.module_package import ModulePackage
from ..utils.plugin_utils import PluginUtils, logger
from .about_dialog import AboutDialog
from .settings_dialog import SettingsDialog

libs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "libs"))
if libs_path not in sys.path:
    sys.path.insert(0, libs_path)

from .database_connection_widget import DatabaseConnectionWidget  # noqa: E402
from .logs_widget import LogsWidget  # noqa: E402
from .module_selection_widget import ModuleSelectionWidget  # noqa: E402
from .module_widget import ModuleWidget  # noqa: E402
from .plugin_widget import PluginWidget  # noqa: E402
from .project_widget import ProjectWidget  # noqa: E402

DIALOG_UI = PluginUtils.get_ui_class("main_dialog.ui")


class MainDialog(QDialog, DIALOG_UI):

    def __init__(self, modules_config_path, about_dialog_cls=None, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        self.__about_dialog_cls = about_dialog_cls or AboutDialog

        self.buttonBox.rejected.connect(self.__closeDialog)
        self.buttonBox.helpRequested.connect(self.__helpRequested)

        # Init GUI Modules
        self.__moduleSelectionWidget = ModuleSelectionWidget(modules_config_path, self)
        self.moduleSelection_groupBox.layout().addWidget(self.__moduleSelectionWidget)

        # Init GUI Database
        self.__databaseConnectionWidget = DatabaseConnectionWidget(self)
        self.db_groupBox.layout().addWidget(self.__databaseConnectionWidget)

        # Init GUI Module Info
        self.__moduleWidget = ModuleWidget(self)
        self.module_tab.layout().addWidget(self.__moduleWidget)

        # Init GUI Project
        self.__projectWidget = ProjectWidget(self)
        self.project_tab.layout().addWidget(self.__projectWidget)

        # Init GUI Plugin
        self.__pluginWidget = PluginWidget(self)
        self.plugin_tab.layout().addWidget(self.__pluginWidget)

        # Init GUI Logs
        self.__logsWidget = LogsWidget(self)
        self.logs_groupBox.layout().addWidget(self.__logsWidget)

        # Add menubar
        self.menubar = QMenuBar(self)
        # On macOS, setNativeMenuBar(False) to show the menu bar inside the dialog window
        if sys.platform == "darwin":
            self.menubar.setNativeMenuBar(False)
        self.layout().setMenuBar(self.menubar)

        # Settings menu
        settings_menu = self.menubar.addMenu(self.tr("Settings"))

        # Settings dialog action
        settings_dialog_action = QAction(self.tr("Preferences..."), self)
        settings_dialog_action.triggered.connect(self.__open_settings_dialog)
        settings_menu.addAction(settings_dialog_action)

        # Cache cleanup action
        cleanup_cache_action = QAction(self.tr("Cleanup Cache"), self)
        cleanup_cache_action.triggered.connect(self.__cleanup_cache)
        settings_menu.addAction(cleanup_cache_action)

        # Help menu
        help_menu = self.menubar.addMenu(self.tr("Help"))

        # Documentation action
        documentation_action = QAction(
            PluginUtils.get_plugin_icon("help.svg"), self.tr("Documentation"), self
        )
        documentation_action.triggered.connect(PluginUtils.open_documentation)
        help_menu.addAction(documentation_action)

        # About action
        about_action = QAction(
            PluginUtils.get_plugin_icon("oqtopus-logo.png"), self.tr("About"), self
        )
        about_action.triggered.connect(self.__show_about_dialog)
        help_menu.addAction(about_action)

        self.__moduleSelectionWidget.signal_loadingStarted.connect(
            self.__moduleSelection_loadingStarted
        )
        self.__moduleSelectionWidget.signal_loadingFinished.connect(
            self.__moduleSelection_loadingFinished
        )

        self.__databaseConnectionWidget.signal_connectionChanged.connect(
            self.__databaseConnectionWidget_connectionChanged
        )
        self.__databaseConnectionWidget_connectionChanged()

        self.__disable_module_tabs()

        logger.info("Ready.")

    def closeEvent(self, event):
        """Handle window close event (X button) to properly cleanup threads."""
        self.__moduleSelectionWidget.close()
        self.__logsWidget.close()
        event.accept()

    def __closeDialog(self):
        self.__moduleSelectionWidget.close()
        self.__logsWidget.close()
        self.accept()

    def __helpRequested(self):
        help_page = "https://github.com/opengisch/oqtopus"
        logger.info(f"Opening help page {help_page}")
        QDesktopServices.openUrl(QUrl(help_page))

    def __open_settings_dialog(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def __cleanup_cache(self):
        """Delete all cached downloaded data."""
        cache_dir = PluginUtils.plugin_temp_path()

        if not os.path.exists(cache_dir):
            QMessageBox.information(
                self,
                self.tr("Cache Cleanup"),
                self.tr("Cache directory does not exist. Nothing to clean up."),
            )
            return

        # Ask for confirmation
        reply = QMessageBox.question(
            self,
            self.tr("Cleanup Cache"),
            self.tr(
                f"This will delete all cached downloaded data from:\n{cache_dir}\n\n"
                "Downloaded module packages will need to be re-downloaded next time.\n\n"
                "Are you sure you want to continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            # Delete the entire cache directory
            shutil.rmtree(cache_dir)
            # Recreate it empty
            os.makedirs(cache_dir)

            QMessageBox.information(
                self,
                self.tr("Cache Cleanup"),
                self.tr("Cache has been successfully cleaned up."),
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Cache Cleanup Error"),
                self.tr(f"Failed to cleanup cache:\n{str(e)}"),
            )

    def __show_about_dialog(self):
        dialog = self.__about_dialog_cls(self)
        dialog.exec()

    def __disable_module_tabs(self):
        """Disable all module-related tabs."""
        self.module_tab.setEnabled(False)
        self.plugin_tab.setEnabled(False)
        self.project_tab.setEnabled(False)

    def __enable_module_tabs(self, module_package: ModulePackage):
        """Enable module tabs based on available assets."""
        self.module_tab.setEnabled(True)
        self.plugin_tab.setEnabled(module_package.asset_plugin is not None)
        self.project_tab.setEnabled(module_package.asset_project is not None)

    def __clear_module_packages(self):
        """Clear module package state from all widgets."""
        self.__moduleWidget.clearModulePackage()
        self.__projectWidget.clearModulePackage()
        self.__pluginWidget.clearModulePackage()

    def __set_module_packages(self, module_package: ModulePackage):
        """Set module package in all widgets."""
        self.__moduleWidget.setModulePackage(module_package)
        self.__projectWidget.setModulePackage(module_package)
        self.__pluginWidget.setModulePackage(module_package)

    def __moduleSelection_loadingStarted(self):
        self.db_groupBox.setEnabled(False)
        self.__disable_module_tabs()
        self.__clear_module_packages()

    def __moduleSelection_loadingFinished(self):
        self.db_groupBox.setEnabled(True)

        module_package = self.__moduleSelectionWidget.getSelectedModulePackage()
        if module_package is None or self.__moduleSelectionWidget.lastError() is not None:
            return

        self.__enable_module_tabs(module_package)
        self.__set_module_packages(module_package)

    def __databaseConnectionWidget_connectionChanged(self):
        self.__moduleWidget.setDatabaseConnection(self.__databaseConnectionWidget.getConnection())

        self.__projectWidget.setService(self.__databaseConnectionWidget.getService())
