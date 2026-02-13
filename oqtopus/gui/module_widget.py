import os
from pathlib import Path

import psycopg
import yaml
from qgis.PyQt.QtCore import QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QMessageBox, QTextBrowser, QWidget

from ..core.module import Module
from ..core.module_operation_task import ModuleOperationTask
from ..core.module_package import ModulePackage
from ..libs.pum.pum_config import PumConfig
from ..libs.pum.schema_migrations import SchemaMigrations
from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import CriticalMessageBox, QtUtils
from .recreate_app_dialog import RecreateAppDialog

DIALOG_UI = PluginUtils.get_ui_class("module_widget.ui")


class ModuleWidget(QWidget, DIALOG_UI):

    signal_operationFinished = pyqtSignal()

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)

        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageInstall)

        # Replace installation info QLabels with QTextBrowser for scrollable content
        for label_name in (
            "moduleInfo_installation_label_install",
            "moduleInfo_installation_label_upgrade",
            "moduleInfo_installation_label_maintain",
        ):
            self.__replace_label_with_text_browser(label_name)

        self.db_demoData_checkBox.clicked.connect(
            lambda checked: self.db_demoData_comboBox.setEnabled(checked)
        )

        self.moduleInfo_install_pushButton.clicked.connect(self.__installModuleClicked)
        self.moduleInfo_upgrade_pushButton.clicked.connect(self.__upgradeModuleClicked)
        self.moduleInfo_roles_pushButton.clicked.connect(self.__rolesClicked)
        self.moduleInfo_drop_app_pushButton.clicked.connect(self.__dropAppClicked)
        self.moduleInfo_recreate_app_pushButton.clicked.connect(self.__recreateAppClicked)
        self.uninstall_button.clicked.connect(self.__uninstallModuleClicked)
        self.uninstall_button_maintain.clicked.connect(self.__uninstallModuleClicked)
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

    def close(self):
        """Clean up resources when the widget is closed."""
        # Cancel any running operations
        if self.__operation_task.isRunning():
            logger.warning("Canceling running operation due to widget close")
            self.__operation_task.cancel()

        # Clean up hook imports to release sys.path and sys.modules entries
        if self.__pum_config is not None:
            try:
                self.__pum_config.cleanup_hook_imports()
            except Exception:
                pass

    def isOperationRunning(self) -> bool:
        """Return True if an operation is currently running."""
        return self.__operation_task.isRunning()

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
        self.__setOperationInProgress(False)

    def __setOperationInProgress(self, in_progress: bool):
        """Enable or disable UI elements based on whether an operation is in progress.

        Args:
            in_progress: True to disable UI (operation starting), False to enable (operation finished)
        """
        # Main operation buttons - disable during operation
        self.moduleInfo_install_pushButton.setEnabled(not in_progress)
        self.db_parameters_CreateAndGrantRoles_upgrade_checkBox.setEnabled(not in_progress)
        self.moduleInfo_upgrade_pushButton.setEnabled(not in_progress)
        self.moduleInfo_roles_pushButton.setEnabled(not in_progress)
        self.uninstall_button.setEnabled(not in_progress)

        # Stacked widget contains all the form controls
        self.moduleInfo_stackedWidget.setEnabled(not in_progress)

        # Cancel button and progress bar - only visible during operation
        self.moduleInfo_cancel_button.setVisible(in_progress)
        self.moduleInfo_cancel_button.setEnabled(in_progress)
        if not in_progress:
            self.moduleInfo_cancel_button.setText(self.tr("Cancel"))

        self.moduleInfo_progressbar.setVisible(in_progress)
        if not in_progress:
            self.moduleInfo_progressbar.setValue(0)

        # Parent controls (module selection, database connection)
        if self.parent() is not None:
            parent_dialog = self.parent()
            if hasattr(parent_dialog, "moduleSelection_groupBox"):
                parent_dialog.moduleSelection_groupBox.setEnabled(not in_progress)
            if hasattr(parent_dialog, "db_groupBox"):
                parent_dialog.db_groupBox.setEnabled(not in_progress)

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
            all_params = self.__pum_config.parameters()
            standard_params = [p for p in all_params if not p.app_only]
            app_only_params = [p for p in all_params if p.app_only]
            self.parameters_groupbox.setParameters(standard_params)
            self.parameters_app_only_groupbox.setParameters(app_only_params)
            self.parameters_groupbox_upgrade.setParameters(standard_params)
            self.parameters_app_only_groupbox_upgrade.setParameters(app_only_params)
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
            parameters = self.__get_all_parameters()

            beta_testing = self.beta_testing_checkbox_pageInstall.isChecked()
            if beta_testing:
                logger.warning("Installing module with beta_testing enabled")

                # Warn user before installing in beta testing mode
                reply = QMessageBox.warning(
                    self,
                    self.tr("Beta Testing Installation"),
                    self.tr(
                        "You are about to install this module in BETA TESTING mode.\n\n"
                        "This means the module will not be allowed to receive future updates "
                        "through normal upgrade process.\n"
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
                "allow_multiple_modules": PluginUtils.get_allow_multiple_modules(),
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
        with self.__database_connection.transaction():
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
                parameters = self.__get_all_parameters()

                beta_testing = self.beta_testing_checkbox_pageUpgrade.isChecked()
                if beta_testing:
                    logger.warning("Upgrading module with beta_testing enabled")

                    # Warn user before upgrading in beta testing mode
                    reply = QMessageBox.warning(
                        self,
                        self.tr("Beta Testing Upgrade"),
                        self.tr(
                            "You are about to upgrade this module in BETA TESTING mode.\n\n"
                            "This means the module will not be allowed to receive future updates "
                            "through normal upgrade process.\n"
                            "We strongly discourage using this for production databases.\n\n"
                            "Are you sure you want to continue?"
                        ),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return

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
        with self.__database_connection.transaction():
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
            parameters = self.__get_all_parameters()

            # Start background uninstall operation
            self.__startOperation("uninstall", parameters, {})

        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't uninstall the module:"), exception, self
            ).exec()
            return

    def __rolesClicked(self):
        """Create and grant roles for the current module."""
        if self.__current_module_package is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please select a module package first."), None, self
            ).exec()
            return

        if self.__database_connection is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please connect to a database first."), None, self
            ).exec()
            return

        if self.__pum_config is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Module configuration not loaded."), None, self
            ).exec()
            return

        try:
            parameters = self.__get_all_parameters()

            # Start background roles operation
            self.__startOperation("roles", parameters, {})

        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't create and grant roles:"), exception, self
            ).exec()
            return

    def __dropAppClicked(self):
        """Execute drop app handlers for the current module."""
        if self.__current_module_package is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please select a module package first."), None, self
            ).exec()
            return

        if self.__database_connection is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please connect to a database first."), None, self
            ).exec()
            return

        if self.__pum_config is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Module configuration not loaded."), None, self
            ).exec()
            return

        reply = QMessageBox.question(
            self,
            self.tr("Drop app"),
            self.tr(
                "Are you sure you want to drop the application?\n\n"
                "This will execute drop app handlers defined in the module configuration."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            parameters = self.__get_all_parameters()

            # Start background drop app operation
            self.__startOperation("drop_app", parameters, {})

        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't drop app:"), exception, self
            ).exec()
            return

    def __recreateAppClicked(self):
        """Execute recreate app (drop + create) handlers for the current module."""
        if self.__current_module_package is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please select a module package first."), None, self
            ).exec()
            return

        if self.__database_connection is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Please connect to a database first."), None, self
            ).exec()
            return

        if self.__pum_config is None:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Module configuration not loaded."), None, self
            ).exec()
            return

        try:
            all_params = self.__pum_config.parameters()
            standard_params = [p for p in all_params if not p.app_only]
            app_only_params = [p for p in all_params if p.app_only]
        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't load parameters:"), exception, self
            ).exec()
            return

        dialog = RecreateAppDialog(standard_params, app_only_params, self)
        if dialog.exec() != RecreateAppDialog.DialogCode.Accepted:
            return

        try:
            parameters = dialog.parameters()

            # Start background recreate app operation
            self.__startOperation("recreate_app", parameters, {})

        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't recreate app:"), exception, self
            ).exec()
            return

    def __get_all_parameters(self) -> dict:
        """Collect parameter values from both standard and app_only groupboxes.

        Uses the upgrade-specific groupboxes when on the upgrade page,
        otherwise uses the install page groupboxes.
        """
        values = {}
        if (
            self.moduleInfo_stackedWidget.currentWidget()
            == self.moduleInfo_stackedWidget_pageUpgrade
        ):
            values.update(self.parameters_groupbox_upgrade.parameters_values())
            values.update(self.parameters_app_only_groupbox_upgrade.parameters_values())
        else:
            values.update(self.parameters_groupbox.parameters_values())
            values.update(self.parameters_app_only_groupbox.parameters_values())
        return values

    def __show_error_state(self, message: str, on_label=None):
        """Display an error state and hide the widget content."""
        label = on_label or self.moduleInfo_selected_label
        label.setText(self.tr(message))
        QtUtils.setForegroundColor(label, PluginUtils.COLOR_WARNING)
        # Hide the stacked widget entirely when in error state
        self.moduleInfo_stackedWidget.setVisible(False)
        # Also disable uninstall buttons since module info is not valid
        self.uninstall_button.setEnabled(False)
        self.uninstall_button_maintain.setEnabled(False)

    def __show_no_module_selected_page(self):
        """Show message when no module package is selected."""
        # Hide the stacked widget since no module is selected
        self.moduleInfo_stackedWidget.setVisible(False)

        # Disable uninstall buttons
        self.uninstall_button.setEnabled(False)
        self.uninstall_button_maintain.setEnabled(False)

    def __show_install_page(self, version: str):
        """Switch to install page and configure it."""
        module_name = self.__current_module_package.module.name
        module_id = self.__current_module_package.module.id
        self.moduleInfo_installation_label_install.setHtml(
            self.tr(f"No module <b>{module_name} ({module_id})</b> installed")
        )
        self.__style_info_label(self.moduleInfo_installation_label_install)
        self.moduleInfo_install_pushButton.setText(self.tr(f"Install {version}"))

        # Configure beta testing checkbox based on package source
        self.__configure_beta_testing_checkbox(self.beta_testing_checkbox_pageInstall)

        # On install, both standard and app_only parameters are editable
        self.parameters_groupbox.setEnabled(True)
        self.parameters_app_only_groupbox.setEnabled(True)

        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageInstall)
        # Ensure the stacked widget is visible when showing a valid page
        self.moduleInfo_stackedWidget.setVisible(True)

    def __replace_label_with_text_browser(self, label_name: str):
        """Replace a QLabel with a QTextBrowser for scrollable installation info."""
        from qgis.PyQt.QtWidgets import QGridLayout

        old_label = getattr(self, label_name)
        parent_layout = old_label.parentWidget().layout()

        browser = QTextBrowser(old_label.parentWidget())
        browser.setObjectName(label_name)
        browser.setReadOnly(True)
        browser.setOpenExternalLinks(False)
        browser.setMaximumHeight(120)
        browser.setFrameShape(QTextBrowser.Shape.NoFrame)

        # Find position in layout and replace
        idx = parent_layout.indexOf(old_label)
        if idx >= 0 and isinstance(parent_layout, QGridLayout):
            row, col, rowspan, colspan = parent_layout.getItemPosition(idx)
            parent_layout.removeWidget(old_label)
            old_label.deleteLater()
            parent_layout.addWidget(browser, row, col, rowspan, colspan)
        else:
            parent_layout.removeWidget(old_label)
            old_label.deleteLater()
            parent_layout.addWidget(browser)

        setattr(self, label_name, browser)

    def __build_installation_text(
        self,
        module_name: str,
        baseline_version: str,
        beta_testing: bool = False,
        schema: str = "",
        installed_date=None,
        upgrade_date=None,
        parameters: dict | None = None,
    ) -> str:
        """Build rich HTML installation info text shown above the action pages."""
        lines = []
        lines.append(f"<b>Module:</b> {module_name}")
        if schema:
            lines.append(f"<b>Schema:</b> {schema}")
        lines.append(f"<b>Version:</b> {baseline_version}")
        if beta_testing:
            lines.append("\u26a0\ufe0f <b>Beta testing</b>")
        if installed_date:
            try:
                lines.append(f"<b>Installed:</b> {installed_date.strftime('%Y-%m-%d %H:%M')}")
            except AttributeError:
                lines.append(f"<b>Installed:</b> {installed_date}")
        if upgrade_date:
            try:
                lines.append(f"<b>Last upgrade:</b> {upgrade_date.strftime('%Y-%m-%d %H:%M')}")
            except AttributeError:
                lines.append(f"<b>Last upgrade:</b> {upgrade_date}")
        if parameters and isinstance(parameters, dict):
            lines.append("<br><b>Parameters:</b>")
            for param_name, param_value in parameters.items():
                lines.append(f"&nbsp;&nbsp;{param_name} = {param_value}")
        return "<br>".join(lines)

    @staticmethod
    def __style_info_label(label, warning: bool = False):
        """Apply a framed style to an installation info label."""
        if warning:
            label.setStyleSheet(
                "QTextBrowser { "
                "  background-color: #fff3cd; "
                "  border: 1px solid #e0c76a; "
                "  border-radius: 4px; "
                "  padding: 6px; "
                "  color: #664d03; "
                "  font-size: 11pt; "
                "}"
            )
        else:
            label.setStyleSheet(
                "QTextBrowser { "
                "  background-color: #f5f5f5; "
                "  border: 1px solid #d0d0d0; "
                "  border-radius: 4px; "
                "  padding: 6px; "
                "  color: #333333; "
                "  font-size: 11pt; "
                "}"
            )

    def __set_installation_label(self, label, install_text: str, beta_testing: bool = False):
        """Set the installation label text and style on the given label widget."""
        label.setHtml(install_text)
        self.__style_info_label(label)

    def __configure_beta_testing_checkbox(self, checkbox):
        """Configure a beta testing checkbox based on the current module package source.

        - Release: disabled and unchecked
        - Dev branch or PR: disabled and checked
        - Zip file: enabled and checked by default
        """
        tooltip = self.tr(
            "If checked, the module is installed in beta testing mode.\n"
            "This means that the module will not be allowed to receive\n"
            "any future updates. We strongly discourage using this\n"
            "for production."
        )
        checkbox.setToolTip(tooltip)

        pkg = self.__current_module_package
        if pkg.type == ModulePackage.Type.FROM_ZIP:
            checkbox.setEnabled(True)
            checkbox.setChecked(True)
        elif (
            pkg.type == ModulePackage.Type.BRANCH
            or pkg.type == ModulePackage.Type.PULL_REQUEST
            or pkg.prerelease
        ):
            checkbox.setEnabled(False)
            checkbox.setChecked(True)
        else:
            # Release
            checkbox.setEnabled(False)
            checkbox.setChecked(False)

    def __show_upgrade_page(
        self,
        module_name: str,
        baseline_version: str,
        target_version: str,
        install_text: str,
        beta_testing: bool = False,
    ):
        """Switch to upgrade page when selected version is newer than installed."""
        self.__set_installation_label(
            self.moduleInfo_installation_label_upgrade, install_text, beta_testing
        )
        self.moduleInfo_selected_label.setText(
            self.tr(f"Module selected: {module_name} - {target_version}")
        )
        QtUtils.resetForegroundColor(self.moduleInfo_selected_label)
        self.moduleInfo_upgrade_pushButton.setText(self.tr(f"Upgrade to {target_version}"))

        # Configure beta testing checkbox based on package source
        self.__configure_beta_testing_checkbox(self.beta_testing_checkbox_pageUpgrade)

        # On upgrade, standard parameters cannot be changed but remain scrollable
        self.parameters_groupbox_upgrade.setParametersEnabled(False)
        self.parameters_app_only_groupbox_upgrade.setParametersEnabled(True)

        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageUpgrade)
        self.moduleInfo_stackedWidget.setVisible(True)

        # Enable upgrade controls
        self.moduleInfo_upgrade_pushButton.setEnabled(True)
        self.db_parameters_CreateAndGrantRoles_upgrade_checkBox.setEnabled(True)

    def __show_maintain_page(
        self,
        module_name: str,
        baseline_version: str,
        target_version: str,
        install_text: str,
        beta_testing: bool = False,
    ):
        """Switch to maintain page when selected version matches installed version."""
        self.__set_installation_label(
            self.moduleInfo_installation_label_maintain, install_text, beta_testing
        )

        # Enable all maintenance buttons
        self.moduleInfo_drop_app_pushButton.setEnabled(True)
        self.moduleInfo_recreate_app_pushButton.setEnabled(True)
        self.moduleInfo_roles_pushButton.setEnabled(True)
        self.uninstall_button_maintain.setEnabled(True)

        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageMaintain)
        self.moduleInfo_stackedWidget.setVisible(True)

        logger.info(
            f"Selected version {target_version} matches installed version {baseline_version}. Showing maintain page."
        )

    def __show_version_mismatch_page(
        self,
        module_name: str,
        baseline_version: str,
        target_version: str,
        install_text: str,
        beta_testing: bool = False,
    ):
        """Switch to maintain page with limited operations when selected version is older than installed."""
        warning_text = (
            install_text
            + "<br><br>"
            + self.tr(
                f"<b>The selected version ({target_version}) is older than the installed version ({baseline_version}).</b><br>"
                f"Maintenance operations are not available. "
                f"Please select the matching version ({baseline_version}) to perform maintenance."
            )
        )
        self.moduleInfo_installation_label_maintain.setHtml(warning_text)
        self.__style_info_label(self.moduleInfo_installation_label_maintain, warning=True)

        # Disable all maintenance buttons
        self.moduleInfo_drop_app_pushButton.setEnabled(False)
        self.moduleInfo_recreate_app_pushButton.setEnabled(False)
        self.moduleInfo_roles_pushButton.setEnabled(False)
        self.uninstall_button_maintain.setEnabled(False)

        self.moduleInfo_stackedWidget.setCurrentWidget(self.moduleInfo_stackedWidget_pageMaintain)
        self.moduleInfo_stackedWidget.setVisible(True)

        logger.info(
            f"Selected version {target_version} is older than installed version {baseline_version}. "
            f"Maintenance operations disabled."
        )

    def __configure_uninstall_button(self):
        """Enable/disable uninstall buttons based on configuration."""
        has_uninstall = bool(
            self.__pum_config
            and self.__pum_config.config.uninstall
            and len(self.__pum_config.config.uninstall) > 0
        )
        self.uninstall_button.setEnabled(has_uninstall)
        self.uninstall_button_maintain.setEnabled(has_uninstall)

    def __updateModuleInfo(self):
        if self.__current_module_package is None:
            self.__show_no_module_selected_page()
            return

        if self.__database_connection is None:
            self.__show_error_state("No database connection available")
            return

        if self.__pum_config is None:
            self.__show_error_state("No PUM config available")
            return

        target_version = self.__pum_config.last_version()
        module_name = self.__current_module_package.module.name
        sm = SchemaMigrations(self.__pum_config)

        self.moduleInfo_stackedWidget.setEnabled(True)
        self.__configure_uninstall_button()

        # Wrap read-only queries in transaction to prevent idle connections
        with self.__database_connection.transaction():
            if sm.exists(self.__database_connection):
                # Module is installed - determine which page to show
                baseline_version = sm.baseline(self.__database_connection)
                migration_summary = sm.migration_summary(self.__database_connection)
                installed_beta_testing = migration_summary.get("beta_testing", False)

                install_text = self.__build_installation_text(
                    module_name,
                    baseline_version,
                    installed_beta_testing,
                    schema=migration_summary.get("schema", ""),
                    installed_date=migration_summary.get("installed_date"),
                    upgrade_date=migration_summary.get("upgrade_date"),
                    parameters=migration_summary.get("parameters"),
                )

                logger.info(
                    f"Version comparison: target={target_version} (type={type(target_version).__name__}), "
                    f"baseline={baseline_version} (type={type(baseline_version).__name__}), "
                    f"target > baseline: {target_version > baseline_version}, "
                    f"target == baseline: {target_version == baseline_version}"
                )

                if target_version > baseline_version:
                    self.__show_upgrade_page(
                        module_name,
                        baseline_version,
                        target_version,
                        install_text,
                        installed_beta_testing,
                    )
                elif target_version == baseline_version:
                    self.__show_maintain_page(
                        module_name,
                        baseline_version,
                        target_version,
                        install_text,
                        installed_beta_testing,
                    )
                else:
                    self.__show_version_mismatch_page(
                        module_name,
                        baseline_version,
                        target_version,
                        install_text,
                        installed_beta_testing,
                    )

                logger.info(f"Migration table details: {migration_summary}")
            else:
                # Module not installed - show install page
                self.__show_install_page(target_version)

    def __startOperation(self, operation: str, parameters: dict, options: dict):
        """Start a background module operation."""
        # Disable UI during operation
        self.__setOperationInProgress(True)

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
        elif operation == "roles":
            self.__operation_task.start_roles(
                self.__pum_config, self.__database_connection, parameters, **options
            )
        elif operation == "drop_app":
            self.__operation_task.start_drop_app(
                self.__pum_config, self.__database_connection, parameters, **options
            )
        elif operation == "recreate_app":
            self.__operation_task.start_recreate_app(
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
            module_name = self.__current_module_package.module.name
            operation = self.__operation_task._ModuleOperationTask__operation
            if operation == "install":
                title = self.tr("Module installed")
                target_version = self.__pum_config.last_version()
                message = self.tr(
                    f"Module '{module_name}' has been installed ({target_version}) successfully."
                )
            elif operation == "upgrade":
                title = self.tr("Module upgraded")
                target_version = self.__pum_config.last_version()
                message = self.tr(
                    f"Module '{module_name}' has been upgraded to {target_version} successfully."
                )
            elif operation == "uninstall":
                title = self.tr("Module uninstalled")
                message = self.tr(f"Module '{module_name}' has been uninstalled successfully.")
            elif operation == "roles":
                title = self.tr("Roles created")
                message = self.tr(
                    f"Roles for module '{module_name}' have been created and granted successfully."
                )
            elif operation == "recreate_app":
                title = self.tr("Application recreated")
                message = self.tr(
                    f"Application schema of module '{module_name}' has been recreated successfully."
                )
            else:
                title = self.tr("Task completed")
                message = self.tr(f"Task on module '{module_name}' completed successfully.")

            QMessageBox.information(
                self,
                title,
                message,
            )
            logger.info(message)

            # Refresh module info
            self.__updateModuleInfo()

            # Signal that an operation finished (for refreshing installed modules list)
            self.signal_operationFinished.emit()
        else:
            # Show error message only if there's an actual error (not just cancellation)
            if error_message:
                CriticalMessageBox(
                    self.tr("Error"),
                    self.tr(f"Operation failed: {error_message}"),
                    None,
                    self,
                ).exec()
