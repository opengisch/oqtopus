import os
from pathlib import Path

import psycopg
import yaml
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QMessageBox, QWidget

from ..core.module import Module
from ..core.module_operation_task import ModuleOperationTask
from ..core.module_package import ModulePackage
from ..libs.pum.pum_config import PumConfig
from ..libs.pum.schema_migrations import SchemaMigrations
from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import CriticalMessageBox, QtUtils

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
        self.moduleInfo_cancel_button.clicked.connect(self.__cancelOperationClicked)

        self.__current_module_package = None
        self.__database_connection = None
        self.__pum_config = None
        self.__data_model_dir = None

        # Background operation task
        self.__operation_task = ModuleOperationTask(self)
        self.__operation_task.signalProgress.connect(self.__onOperationProgress)
        self.__operation_task.signalFinished.connect(self.__onOperationFinished)

        # Timeout timer for detecting hung operations
        self.__cancel_timeout_timer = QTimer(self)
        self.__cancel_timeout_timer.setSingleShot(True)
        self.__cancel_timeout_timer.timeout.connect(self.__onCancelTimeout)

        # Hide cancel button and progress bar initially
        self.moduleInfo_cancel_button.setVisible(False)
        self.moduleInfo_progressbar.setVisible(False)

    def setModulePackage(self, module_package: Module):
        # Clean up old hook imports before loading new version
        if self.__pum_config is not None:
            try:
                self.__pum_config.cleanup_hook_imports()
            except Exception:
                # Ignore errors during cleanup
                pass

        self.__current_module_package = module_package
        self.__packagePrepareGetPUMConfig()
        self.__updateModuleInfo()

    def clearModulePackage(self):
        """Clear module package state and disable the stacked widget."""
        # Cancel any running operations before clearing
        if self.__operation_task.isRunning():
            logger.warning("Canceling running operation due to module package change")
            self.__operation_task.cancel()
            # Don't wait - just reset UI immediately to avoid freezing
            # The finished signal will be emitted when the thread stops

        # Reset UI state immediately
        self.__resetOperationUI()

        # Clean up any imported modules from hooks to prevent conflicts
        if self.__pum_config is not None:
            try:
                self.__pum_config.cleanup_hook_imports()
            except Exception:
                # Ignore errors during cleanup
                pass

        self.__current_module_package = None
        self.__pum_config = None
        self.__data_model_dir = None
        self.__updateModuleInfo()

    def setDatabaseConnection(self, connection: psycopg.Connection):
        # Cancel any running operations before changing database
        if self.__operation_task.isRunning():
            logger.warning("Canceling running operation due to database connection change")
            self.__operation_task.cancel()
            # Don't wait - just reset UI immediately to avoid freezing

        # Reset UI state immediately
        self.__resetOperationUI()

        self.__database_connection = connection
        self.__updateModuleInfo()

    def __resetOperationUI(self):
        """Reset UI elements related to operations."""
        self.moduleInfo_cancel_button.setVisible(False)
        self.moduleInfo_cancel_button.setEnabled(True)
        self.moduleInfo_cancel_button.setText(self.tr("Cancel"))
        self.moduleInfo_progressbar.setVisible(False)
        self.moduleInfo_progressbar.setValue(0)
        self.moduleInfo_stackedWidget.setEnabled(True)

        # Re-enable parent controls if they were disabled
        if self.parent() is not None:
            parent_dialog = self.parent()
            if hasattr(parent_dialog, "moduleSelection_groupBox"):
                parent_dialog.moduleSelection_groupBox.setEnabled(True)
            if hasattr(parent_dialog, "db_groupBox"):
                parent_dialog.db_groupBox.setEnabled(True)

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

        # Check that the module ID in the PUM config matches the selected module
        pum_module_id = self.__pum_config.config.pum.module
        selected_module_id = self.__current_module_package.module.id
        if pum_module_id != selected_module_id:
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(
                    f"Module ID mismatch: The selected module is '{selected_module_id}' but the PUM configuration specifies '{pum_module_id}'."
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

                # Warn user before installing in beta testing mode
                reply = QMessageBox.warning(
                    self,
                    self.tr("Beta Testing Installation"),
                    self.tr(
                        "You are about to install this module in BETA TESTING mode.\n\n"
                        "This means the module will not be allowed to receive future updates through normal upgrade process.\n"
                        "We strongly discourage using this for production databases.\n\n"
                        "Are you sure you want to continue?"
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            # Start background install operation
            options = {
                "roles": self.db_parameters_CreateAndGrantRoles_install_checkBox.isChecked(),
                "grant": self.db_parameters_CreateAndGrantRoles_install_checkBox.isChecked(),
                "beta_testing": beta_testing,
                "install_demo_data": self.db_demoData_checkBox.isChecked(),
                "demo_data_name": (
                    self.db_demoData_comboBox.currentText()
                    if self.db_demoData_checkBox.isChecked()
                    else None
                ),
            }

            self.__startOperation("install", parameters, options)

        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't install the module:"), exception, self
            ).exec()
            return

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

        # Check that the module ID in the PUM config matches the selected module
        pum_module_id = self.__pum_config.config.pum.module
        selected_module_id = self.__current_module_package.module.id
        if pum_module_id != selected_module_id:
            CriticalMessageBox(
                self.tr("Error"),
                self.tr(
                    f"Module ID mismatch: The selected module is '{selected_module_id}' but the PUM configuration specifies '{pum_module_id}'."
                ),
                None,
                self,
            ).exec()
            return

        # Check that the module ID matches the installed module in the database
        sm = SchemaMigrations(self.__pum_config)
        installed_beta_testing = False
        if sm.exists(self.__database_connection):
            migration_details = sm.migration_details(self.__database_connection)
            installed_module_id = migration_details.get("module")
            installed_beta_testing = migration_details.get("beta_testing", False)

            if installed_module_id and installed_module_id != pum_module_id:
                CriticalMessageBox(
                    self.tr("Error"),
                    self.tr(
                        f"Module ID mismatch: The database contains module '{installed_module_id}' but you are trying to upgrade with '{pum_module_id}'."
                    ),
                    None,
                    self,
                ).exec()
                return

            # Confirm upgrade if installed module is in beta testing
            if installed_beta_testing:
                reply = QMessageBox.question(
                    self,
                    self.tr("Confirm Upgrade"),
                    self.tr(
                        "The installed module is in BETA TESTING mode.\n\n"
                        "Are you sure you want to upgrade? \n"
                        "This is not a recommended action: \n"
                        "if the installed version has missing or different changelogs, \n"
                        "the upgrade may fail or cause further issues."
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
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

            # Start background upgrade operation
            options = {
                "beta_testing": beta_testing,
                "force": installed_beta_testing,
                "roles": self.db_parameters_CreateAndGrantRoles_upgrade_checkBox.isChecked(),
                "grant": self.db_parameters_CreateAndGrantRoles_upgrade_checkBox.isChecked(),
            }

            self.__startOperation("upgrade", parameters, options)

        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't upgrade the module:"), exception, self
            ).exec()
            return

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

            # Start background uninstall operation
            self.__startOperation("uninstall", parameters, {})

        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't uninstall the module:"), exception, self
            ).exec()
            return

    def __show_error_state(self, message: str, on_label=None):
        """Display an error state and hide the widget content."""
        label = on_label or self.moduleInfo_selected_label
        label.setText(self.tr(message))
        QtUtils.setForegroundColor(label, PluginUtils.COLOR_WARNING)
        # Hide the stacked widget entirely when in error state
        self.moduleInfo_stackedWidget.setVisible(False)
        # Also hide uninstall button since module info is not valid
        self.uninstall_button.setVisible(False)

    def __show_install_page(self, version: str):
        """Switch to install page and configure it."""
        self.moduleInfo_installation_label.setText(self.tr("No module installed"))
        QtUtils.resetForegroundColor(self.moduleInfo_installation_label)
        self.moduleInfo_install_pushButton.setText(self.tr(f"Install {version}"))
        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageInstall)
        # Ensure the stacked widget is visible when showing a valid page
        self.moduleInfo_stackedWidget.setVisible(True)

    def __show_upgrade_page(
        self,
        module_name: str,
        baseline_version: str,
        target_version: str,
        beta_testing: bool = False,
    ):
        """Switch to upgrade page and configure it."""
        beta_text = " (BETA TESTING)" if beta_testing else ""
        self.moduleInfo_installation_label.setText(
            f"Installed: module {module_name} at version {baseline_version}{beta_text}."
        )
        if beta_testing:
            QtUtils.setForegroundColor(
                self.moduleInfo_installation_label, PluginUtils.COLOR_WARNING
            )
        else:
            QtUtils.resetForegroundColor(self.moduleInfo_installation_label)
        self.moduleInfo_upgrade_pushButton.setText(self.tr(f"Upgrade to {target_version}"))
        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageUpgrade)
        # Ensure the stacked widget is visible when showing a valid page
        self.moduleInfo_stackedWidget.setVisible(True)

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
        has_uninstall = bool(
            self.__pum_config
            and self.__pum_config.config.uninstall
            and len(self.__pum_config.config.uninstall) > 0
        )
        self.uninstall_button.setVisible(has_uninstall)

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

        # Wrap read-only queries in transaction to prevent idle connections
        with self.__database_connection.transaction():
            if sm.exists(self.__database_connection):
                # Module is installed - show upgrade page
                baseline_version = sm.baseline(self.__database_connection)
                migration_details = sm.migration_details(self.__database_connection)
                installed_beta_testing = migration_details.get("beta_testing", False)
                self.__show_upgrade_page(
                    self.__current_module_package.module.name,
                    baseline_version,
                    migrationVersion,
                    installed_beta_testing,
                )

                logger.info(f"Migration table details: {migration_details}")
            else:
                # Module not installed - show install page
                self.__show_install_page(migrationVersion)

    def __startOperation(self, operation: str, parameters: dict, options: dict):
        """Start a background module operation."""
        # Disable UI during operation
        self.moduleInfo_stackedWidget.setEnabled(False)
        self.moduleInfo_cancel_button.setVisible(True)
        self.moduleInfo_cancel_button.setEnabled(True)
        self.moduleInfo_progressbar.setVisible(True)
        self.moduleInfo_progressbar.setValue(0)

        # Disable module selection and database connection to prevent navigation during operation
        if self.parent() is not None:
            parent_dialog = self.parent()
            if hasattr(parent_dialog, "moduleSelection_groupBox"):
                parent_dialog.moduleSelection_groupBox.setEnabled(False)
            if hasattr(parent_dialog, "db_groupBox"):
                parent_dialog.db_groupBox.setEnabled(False)

        # Start the background task
        if operation == "install":
            self.__operation_task.start_install(
                self.__pum_config, self.__database_connection, parameters, **options
            )
        elif operation == "upgrade":
            self.__operation_task.start_upgrade(
                self.__pum_config, self.__database_connection, parameters, **options
            )
        elif operation == "uninstall":
            self.__operation_task.start_uninstall(
                self.__pum_config, self.__database_connection, parameters, **options
            )

    def __cancelOperationClicked(self):
        """Cancel the current operation."""
        self.moduleInfo_cancel_button.setEnabled(False)
        self.moduleInfo_cancel_button.setText(self.tr("Canceling..."))
        self.__operation_task.cancel()
        logger.info("Operation cancel requested by user")
        # Don't wait here - the __onOperationFinished signal will handle UI cleanup

        # Start a timeout timer in case the operation hangs
        self.__cancel_timeout_timer.start(5000)  # 5 second timeout

    def __onCancelTimeout(self):
        """Handle timeout when cancel doesn't complete."""
        if self.__operation_task.isRunning():
            logger.error("Operation did not respond to cancel request, forcing termination")
            self.__operation_task.terminate()
            # Force UI reset
            self.__resetOperationUI()
            # Show warning
            QMessageBox.warning(
                self,
                self.tr("Operation Terminated"),
                self.tr(
                    "The operation did not respond to the cancel request and was forcefully terminated. "
                    "The database may be in an inconsistent state. Please verify manually."
                ),
            )

    def __onOperationProgress(self, message: str, current: int, total: int):
        """Handle progress updates from background operation."""
        # Update progress bar only, don't touch the installation label
        if total > 0:
            # Determinate progress
            self.moduleInfo_progressbar.setFormat(message)
            self.moduleInfo_progressbar.setTextVisible(True)
            self.moduleInfo_progressbar.setMaximum(total)
            self.moduleInfo_progressbar.setValue(current)
            logger.debug(f"Progress update: {current}/{total} - {message}")
        else:
            # Indeterminate progress
            self.moduleInfo_progressbar.setFormat(message)
            self.moduleInfo_progressbar.setTextVisible(True)
            self.moduleInfo_progressbar.setMaximum(0)
            self.moduleInfo_progressbar.setValue(0)

    def __onOperationFinished(self, success: bool, error_message: str):
        """Handle completion of background operation."""
        # Stop the timeout timer if running
        self.__cancel_timeout_timer.stop()

        # Always reset UI state, even if already reset
        self.__resetOperationUI()

        if success:
            # Show success message
            operation_name = (
                "installed"
                if self.__operation_task._ModuleOperationTask__operation == "install"
                else (
                    "upgraded"
                    if self.__operation_task._ModuleOperationTask__operation == "upgrade"
                    else "uninstalled"
                )
            )

            QMessageBox.information(
                self,
                self.tr(f"Module {operation_name}"),
                self.tr(
                    f"Module '{self.__current_module_package.module.name}' has been successfully {operation_name}."
                ),
            )
            logger.info(
                f"Module '{self.__current_module_package.module.name}' has been successfully {operation_name}."
            )

            # Refresh module info
            self.__updateModuleInfo()
        else:
            # Show error message only if there's an actual error (not just cancellation)
            if error_message:
                CriticalMessageBox(
                    self.tr("Error"),
                    self.tr(f"Operation failed: {error_message}"),
                    None,
                    self,
                ).exec()
