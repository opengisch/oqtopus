import logging

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from ..core.module_package import ModulePackage
from ..libs.pum import ParameterDefinition
from .parameters_groupbox import ParametersGroupBox
from .roles_groupbox import RolesGroupBox

logger = logging.getLogger(__name__)


class UpgradeDialog(QDialog):
    """Dialog for confirming module upgrade with parameter review/editing."""

    def __init__(
        self,
        module_package: ModulePackage,
        standard_params: list[ParameterDefinition],
        app_only_params: list[ParameterDefinition],
        target_version: str,
        installed_parameters: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr(f"Upgrade to {target_version}"))
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Description
        description = QLabel(
            self.tr(
                f"You are about to upgrade to version <b>{target_version}</b>.\n\n"
                "Please review the parameters and options below."
            ),
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Standard parameters (read-only on upgrade)
        self.__standard_groupbox = ParametersGroupBox(self)
        self.__standard_groupbox.setTitle(self.tr("Parameters"))
        gb_layout = QVBoxLayout()
        gb_layout.setContentsMargins(3, 3, 3, 3)
        self.__standard_groupbox.setLayout(gb_layout)
        self.__standard_groupbox.setParameters(standard_params)
        self.__standard_groupbox.setParametersEnabled(False)
        if installed_parameters:
            self.__standard_groupbox.setParameterValues(installed_parameters)
        layout.addWidget(self.__standard_groupbox)

        # App-only parameters (editable)
        self.__app_only_groupbox = ParametersGroupBox(self)
        self.__app_only_groupbox.setTitle(self.tr("Application parameters"))
        gb_layout = QVBoxLayout()
        gb_layout.setContentsMargins(3, 3, 3, 3)
        self.__app_only_groupbox.setLayout(gb_layout)
        self.__app_only_groupbox.setParameters(app_only_params)
        if installed_parameters:
            self.__app_only_groupbox.setParameterValues(installed_parameters)
        layout.addWidget(self.__app_only_groupbox)

        # Beta testing checkbox
        self.__beta_testing_checkbox = QCheckBox(self.tr("Beta testing"), self)
        self.__configure_beta_testing_checkbox(module_package)
        layout.addWidget(self.__beta_testing_checkbox)

        # Roles
        self.__roles_groupbox = RolesGroupBox(self)
        layout.addWidget(self.__roles_groupbox)

        # Add stretch to push buttons to the bottom
        layout.addStretch()

        # Upgrade / Cancel buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText(
            self.tr(f"Upgrade to {target_version}")
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self):
        """Override accept to warn about beta testing before confirming."""
        if self.__beta_testing_checkbox.isChecked():
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
        super().accept()

    def __configure_beta_testing_checkbox(self, module_package: ModulePackage):
        """Configure beta testing checkbox based on the module package source."""
        tooltip = self.tr(
            "If checked, the module is installed in beta testing mode.\n"
            "This means that the module will not be allowed to receive\n"
            "any future updates. We strongly discourage using this\n"
            "for production."
        )
        self.__beta_testing_checkbox.setToolTip(tooltip)

        if module_package.type == ModulePackage.Type.FROM_ZIP:
            self.__beta_testing_checkbox.setEnabled(True)
            self.__beta_testing_checkbox.setChecked(True)
        elif (
            module_package.type == ModulePackage.Type.BRANCH
            or module_package.type == ModulePackage.Type.PULL_REQUEST
            or module_package.prerelease
        ):
            self.__beta_testing_checkbox.setEnabled(False)
            self.__beta_testing_checkbox.setChecked(True)
        else:
            self.__beta_testing_checkbox.setEnabled(False)
            self.__beta_testing_checkbox.setChecked(False)

    def parameters(self) -> dict:
        """Return combined parameter values from both groupboxes."""
        values = {}
        values.update(self.__standard_groupbox.parameters_values())
        values.update(self.__app_only_groupbox.parameters_values())
        return values

    def beta_testing(self) -> bool:
        """Return whether beta testing is checked."""
        return self.__beta_testing_checkbox.isChecked()

    def roles(self) -> bool:
        """Return whether create and grant roles is checked."""
        return self.__roles_groupbox.isChecked()

    def roles_options(self) -> dict:
        """Return the full roles options dict."""
        return self.__roles_groupbox.roles_options()
