import os

import psycopg
from pum.pum_config import PumConfig
from pum.schema_migrations import SchemaMigrations
from pum.upgrader import Upgrader
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox, QWidget

from ..core.module import Module
from ..core.module_package import ModulePackage
from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import CriticalMessageBox, OverrideCursor, QtUtils

DIALOG_UI = PluginUtils.get_ui_class("module_widget.ui")


class ModuleWidget(QWidget, DIALOG_UI):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)

        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageInstall)

        self.db_demoData_checkBox.clicked.connect(
            lambda checked: self.db_demoData_comboBox.setEnabled(checked)
        )

        self.moduleInfo_install_pushButton.clicked.connect(self.__installModuleClicked)
        self.moduleInfo_upgrade_pushButton.clicked.connect(self.__upgradeModuleClicked)

        self.__current_module_package = None
        self.__database_connection = None

    def setModulePackage(self, module_package: Module):
        self.__current_module_package = module_package
        self.__packagePrepareGetPUMConfig()
        self.__updateModuleInfo()

    def setDatabaseConnection(self, connection: psycopg.Connection):
        self.__database_connection = connection
        self.__updateModuleInfo()

    def __packagePrepareGetPUMConfig(self):
        package_dir = self.__current_module_package.source_package_dir

        if package_dir is None:
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(
                    f"The selected file '{self.__current_module_package.source_package_zip}' does not contain a valid package directory."
                ),
                None,
                self,
            ).exec()
            return

        self.__data_model_dir = os.path.join(package_dir, "datamodel")
        pumConfigFilename = os.path.join(self.__data_model_dir, ".pum.yaml")
        if not os.path.exists(pumConfigFilename):
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(
                    f"The selected file '{self.__current_module_package.source_package_zip}' does not contain a valid .pum.yaml file."
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

        try:
            self.parameters_groupbox.setParameters(self.__pum_config.parameters())
        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(f"Can't load parameters from PUM config '{pumConfigFilename}':"),
                exception,
                self,
            ).exec()
            return

        self.db_demoData_comboBox.clear()
        for demo_data_name, demo_data_file in self.__pum_config.demo_data().items():
            self.db_demoData_comboBox.addItem(demo_data_name, demo_data_file)

    def __installModuleClicked(self):

        if self.__current_module_package is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please select a module package first."), None, self
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

        try:
            parameters = self.parameters_groupbox.parameters_values()

            beta_testing = False
            if (
                self.__current_module_package.type == ModulePackage.Type.PULL_REQUEST
                or self.__current_module_package.type == ModulePackage.Type.BRANCH
            ):
                logger.warning(
                    "Installing module from branch or pull request: set parameter beta_testing to True"
                )
                beta_testing = True

            upgrader = Upgrader(
                config=self.__pum_config,
            )
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                upgrader.install(
                    parameters=parameters,
                    connection=self.__database_connection,
                    roles=self.db_parameters_CreateAndGrantRoles_checkBox.isChecked(),
                    grant=self.db_parameters_CreateAndGrantRoles_checkBox.isChecked(),
                    beta_testing=beta_testing,
                )

                if self.db_demoData_checkBox.isChecked():
                    demo_data_name = self.db_demoData_comboBox.currentText()
                    upgrader.install_demo_data(
                        connection=self.__database_connection,
                        name=demo_data_name,
                        parameters=parameters,
                    )
        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't install the module:"), exception, self
            ).exec()
            return

        QMessageBox.information(
            self,
            self.tr("Module installed"),
            self.tr(
                f"Module '{self.__current_module_package.module.name}' version '{self.__current_module_package.name}' has been successfully installed."
            ),
        )
        logger.info(
            f"Module '{self.__current_module_package.module.name}' version '{self.__current_module_package.name}' has been successfully installed."
        )

        self.__updateModuleInfo()

    def __upgradeModuleClicked(self):
        QMessageBox.critical(
            self,
            self.tr("Not implemented"),
            self.tr("Upgrade module is not implemented yet."),
        )
        return

    def __updateModuleInfo(self):
        if self.__current_module_package is None:
            self.moduleInfo_label.setText(self.tr("No module package selected"))
            QtUtils.setForegroundColor(self.moduleInfo_label, PluginUtils.COLOR_WARNING)
            return

        if self.__database_connection is None:
            self.moduleInfo_label.setText(self.tr("No database connection available"))
            QtUtils.setForegroundColor(self.moduleInfo_label, PluginUtils.COLOR_WARNING)
            return

        if self.__pum_config is None:
            self.moduleInfo_label.setText(self.tr("No PUM config available"))
            QtUtils.setForegroundColor(self.moduleInfo_label, PluginUtils.COLOR_WARNING)
            return

        migrationVersion = self.__pum_config.last_version()
        sm = SchemaMigrations(self.__pum_config)

        if sm.exists(self.__database_connection):
            # Case upgrade
            baseline_version = sm.baseline(self.__database_connection)
            self.moduleInfo_label.setText(self.tr(f"Version {baseline_version} found"))
            QtUtils.resetForegroundColor(self.moduleInfo_label)
            self.moduleInfo_upgrade_pushButton.setText(self.tr(f"Upgrade to {migrationVersion}"))

            self.moduleInfo_stackedWidget.setCurrentWidget(
                self.moduleInfo_stackedWidget_pageUpgrade
            )

            logger.info(
                f"Migration table details: {sm.migration_details(self.__database_connection)}"
            )

        else:
            # Case install
            self.moduleInfo_label.setText(self.tr("No module found"))
            QtUtils.resetForegroundColor(self.moduleInfo_label)
            self.moduleInfo_install_pushButton.setText(self.tr(f"Install {migrationVersion}"))
            self.moduleInfo_stackedWidget.setCurrentWidget(
                self.moduleInfo_stackedWidget_pageInstall
            )
