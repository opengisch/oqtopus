import os
from pathlib import Path

import psycopg
import yaml
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
        self.uninstall_button.clicked.connect(self.__uninstallModuleClicked)

        self.__current_module_package = None
        self.__database_connection = None
        self.__pum_config = None
        self.__data_model_dir = None

    def setModulePackage(self, module_package: Module):
        self.__current_module_package = module_package
        self.__packagePrepareGetPUMConfig()
        self.__updateModuleInfo()

    def clearModulePackage(self):
        """Clear module package state and disable the stacked widget."""
        self.__current_module_package = None
        self.__pum_config = None
        self.__data_model_dir = None
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
                    f"The selected file '{self.__current_module_package.source_package_zip}' doesn't contain a valid package directory."
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
                    f"The selected file '{self.__current_module_package.source_package_zip}' doesn't contain a valid .pum.yaml file."
                ),
                None,
                self,
            ).exec()
            return

        try:
            with open(pumConfigFilename) as file:
                # since pum 1.3, the module id is mandatory in the pum config
                config_data = yaml.safe_load(file)
                if "pum" not in config_data:
                    config_data["pum"] = {}
                if "module" not in config_data["pum"]:
                    config_data["pum"]["module"] = self.__current_module_package.module.id
                base_path = Path(pumConfigFilename).parent
            self.__pum_config = PumConfig(
                base_path=base_path, install_dependencies=True, **config_data
            )
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

        # Check that the module name in the PUM config matches the selected module
        pum_module_name = self.__pum_config.config.pum.module
        selected_module_name = self.__current_module_package.module.id
        if pum_module_name != selected_module_name:
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(
                    f"Module name mismatch: The selected module is '{selected_module_name}' but the PUM configuration specifies '{pum_module_name}'."
                ),
                None,
                self,
            ).exec()
            return

        try:
            parameters = self.parameters_groupbox.parameters_values()

            beta_testing = False
            if (
                self.__current_module_package.type == ModulePackage.Type.PULL_REQUEST
                or self.__current_module_package.type == ModulePackage.Type.BRANCH
                or self.__current_module_package.prerelease
            ):
                logger.warning(
                    "Installing module from branch, pull request, or prerelease: set parameter beta_testing to True"
                )
                beta_testing = True

            upgrader = Upgrader(
                config=self.__pum_config,
            )
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                upgrader.install(
                    parameters=parameters,
                    connection=self.__database_connection,
                    roles=self.db_parameters_CreateAndGrantRoles_install_checkBox.isChecked(),
                    grant=self.db_parameters_CreateAndGrantRoles_install_checkBox.isChecked(),
                    beta_testing=beta_testing,
                    commit=False,
                )

                if self.db_demoData_checkBox.isChecked():
                    demo_data_name = self.db_demoData_comboBox.currentText()
                    upgrader.install_demo_data(
                        connection=self.__database_connection,
                        name=demo_data_name,
                        parameters=parameters,
                    )

                self.__database_connection.commit()

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

        # Check that the module name in the PUM config matches the selected module
        pum_module_name = self.__pum_config.config.pum.module
        selected_module_name = self.__current_module_package.module.name
        if pum_module_name != selected_module_name:
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(
                    f"Module name mismatch: The selected module is '{selected_module_name}' but the PUM configuration specifies '{pum_module_name}'."
                ),
                None,
                self,
            ).exec()
            return

        # Check that the module name matches the installed module in the database
        sm = SchemaMigrations(self.__pum_config)
        if sm.exists(self.__database_connection):
            migration_details = sm.migration_details(self.__database_connection)
            installed_module_name = migration_details.get("module")
            if installed_module_name and installed_module_name != pum_module_name:
                CriticalMessageBox(
                    self.tr("Error"),
                    self.tr(
                        f"Module name mismatch: The database contains module '{installed_module_name}' but you are trying to upgrade with '{pum_module_name}'."
                    ),
                    None,
                    self,
                ).exec()
                return

        try:
            parameters = self.parameters_groupbox.parameters_values()

            beta_testing = False
            if (
                self.__current_module_package.type == ModulePackage.Type.PULL_REQUEST
                or self.__current_module_package.type == ModulePackage.Type.BRANCH
                or self.__current_module_package.prerelease
            ):
                logger.warning(
                    "Upgrading module from branch, pull request, or prerelease: set parameter beta_testing to True"
                )
                beta_testing = True

            upgrader = Upgrader(
                config=self.__pum_config,
            )
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                upgrader.upgrade(
                    parameters=parameters,
                    connection=self.__database_connection,
                    beta_testing=beta_testing,
                    roles=self.db_parameters_CreateAndGrantRoles_upgrade_checkBox.isChecked(),
                    grant=self.db_parameters_CreateAndGrantRoles_upgrade_checkBox.isChecked(),
                )

                self.__database_connection.commit()

        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't upgrade the module:"), exception, self
            ).exec()
            return

        QMessageBox.information(
            self,
            self.tr("Module upgraded"),
            self.tr(
                f"Module '{self.__current_module_package.module.name}' has been successfully upgraded to version '{self.__current_module_package.name}'."
            ),
        )
        logger.info(
            f"Module '{self.__current_module_package.module.name}' has been successfully upgraded to version '{self.__current_module_package.name}'."
        )

        self.__updateModuleInfo()

    def __uninstallModuleClicked(self):
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

        # Check if uninstall hooks are defined
        if not self.__pum_config.config.uninstall:
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(
                    "No uninstall configuration found. The module does not provide uninstall functionality."
                ),
                None,
                self,
            ).exec()
            return

        # Check if the installed version matches the selected version
        sm = SchemaMigrations(self.__pum_config)
        version_warning = ""
        if not sm.exists(self.__database_connection):
            raise Exception("Module is not installed in the database. This should not happen.")
        installed_version = sm.baseline(self.__database_connection)
        selected_version = self.__pum_config.last_version()
        if installed_version != selected_version:
            version_warning = (
                f"\n\n⚠️ WARNING: Version mismatch detected!\n"
                f"Installed version: {installed_version}\n"
                f"Selected version: {selected_version}\n\n"
                f"This could be an issue as the uninstall instructions may not match the installed datamodel."
            )

        # Confirm uninstall with user
        reply = QMessageBox.question(
            self,
            self.tr("Confirm Uninstall"),
            self.tr(
                f"Are you sure you want to uninstall module '{self.__current_module_package.module.name}'?\n\n"
                f"This action will remove all module data from the database and cannot be undone."
                f"{version_warning}"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            parameters = self.parameters_groupbox.parameters_values()

            upgrader = Upgrader(
                config=self.__pum_config,
            )
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                upgrader.uninstall(
                    connection=self.__database_connection,
                    parameters=parameters,
                    commit=True,
                )

        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't uninstall the module:"), exception, self
            ).exec()
            return

        QMessageBox.information(
            self,
            self.tr("Module uninstalled"),
            self.tr(
                f"Module '{self.__current_module_package.module.name}' has been successfully uninstalled."
            ),
        )
        logger.info(
            f"Module '{self.__current_module_package.module.name}' has been successfully uninstalled."
        )

        self.__updateModuleInfo()

    def __show_error_state(self, message: str, on_label=None):
        """Display an error state and disable the widget."""
        label = on_label or self.moduleInfo_selected_label
        label.setText(self.tr(message))
        QtUtils.setForegroundColor(label, PluginUtils.COLOR_WARNING)
        self.moduleInfo_stackedWidget.setEnabled(False)

    def __show_install_page(self, version: str):
        """Switch to install page and configure it."""
        self.moduleInfo_installation_label.setText(self.tr("No module installed"))
        QtUtils.resetForegroundColor(self.moduleInfo_installation_label)
        self.moduleInfo_install_pushButton.setText(self.tr(f"Install {version}"))
        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageInstall)

    def __show_upgrade_page(self, module_name: str, baseline_version: str, target_version: str):
        """Switch to upgrade page and configure it."""
        self.moduleInfo_installation_label.setText(
            f"Installed: module {module_name} at version {baseline_version}."
        )
        QtUtils.resetForegroundColor(self.moduleInfo_installation_label)
        self.moduleInfo_upgrade_pushButton.setText(self.tr(f"Upgrade to {target_version}"))
        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageUpgrade)

        # Enable/disable upgrade button based on version comparison
        if target_version <= baseline_version:
            self.moduleInfo_upgrade_pushButton.setDisabled(True)
            logger.info(
                f"Selected version {target_version} is equal to or lower than installed version {baseline_version}"
            )
        else:
            self.moduleInfo_upgrade_pushButton.setEnabled(True)

    def __configure_uninstall_button(self):
        """Show/hide uninstall button based on configuration."""
        self.uninstall_button.setVisible(
            self.__pum_config.config.uninstall if self.__pum_config else False
        )

    def __updateModuleInfo(self):
        if self.__current_module_package is None:
            self.__show_error_state("No module package selected")
            return

        if self.__database_connection is None:
            self.__show_error_state(
                "No database connection available", on_label=self.moduleInfo_installation_label
            )
            return

        if self.__pum_config is None:
            self.__show_error_state("No PUM config available")
            return

        migrationVersion = self.__pum_config.last_version()
        sm = SchemaMigrations(self.__pum_config)

        # Set the selected module info
        self.moduleInfo_selected_label.setText(
            self.tr(
                f"Module selected:{self.__current_module_package.module.name} - {migrationVersion}"
            )
        )
        QtUtils.resetForegroundColor(self.moduleInfo_selected_label)

        self.moduleInfo_stackedWidget.setEnabled(True)
        self.__configure_uninstall_button()

        if sm.exists(self.__database_connection):
            # Module is installed - show upgrade page
            baseline_version = sm.baseline(self.__database_connection)
            self.__show_upgrade_page(
                self.__current_module_package.module.name, baseline_version, migrationVersion
            )

            logger.info(
                f"Migration table details: {sm.migration_details(self.__database_connection)}"
            )
        else:
            # Module not installed - show install page
            self.__show_install_page(migrationVersion)
