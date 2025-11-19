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
import sys

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    # Import for Qt5
    from qgis.PyQt.QtWidgets import QAction

from qgis.PyQt.QtWidgets import (
    QDialog,
    QMenuBar,
)

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

        # Settings action
        settings_action = QAction(self.tr("Settings"), self)
        settings_action.triggered.connect(self.__open_settings_dialog)
        self.menubar.addAction(settings_action)

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

        self.module_tab.setEnabled(False)
        self.plugin_tab.setEnabled(False)
        self.project_tab.setEnabled(False)

        logger.info("Ready.")

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

    def __show_about_dialog(self):
        dialog = self.__about_dialog_cls(self)
        dialog.exec()

    def __moduleSelection_loadingStarted(self):
        self.db_groupBox.setEnabled(False)
        self.module_tab.setEnabled(False)
        self.plugin_tab.setEnabled(False)
        self.project_tab.setEnabled(False)

    def __moduleSelection_loadingFinished(self):
        self.db_groupBox.setEnabled(True)

        module_package = self.__moduleSelectionWidget.getSelectedModulePackage()
        if module_package is None:
            return

        if self.__moduleSelectionWidget.lastError() is not None:
            return

        self.module_tab.setEnabled(True)

        if module_package.asset_plugin is not None:
            self.plugin_tab.setEnabled(True)

        if module_package.asset_project is not None:
            self.project_tab.setEnabled(True)

        self.__moduleWidget.setModulePackage(
            self.__moduleSelectionWidget.getSelectedModulePackage()
        )
        self.__projectWidget.setModulePackage(
            self.__moduleSelectionWidget.getSelectedModulePackage()
        )

        self.__pluginWidget.setModulePackage(
            self.__moduleSelectionWidget.getSelectedModulePackage()
        )

    def __databaseConnectionWidget_connectionChanged(self):
        self.__moduleWidget.setDatabaseConnection(self.__databaseConnectionWidget.getConnection())

        self.__projectWidget.setService(self.__databaseConnectionWidget.getService())
