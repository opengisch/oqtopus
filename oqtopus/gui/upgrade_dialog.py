import logging

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from ..core.module_package import ModulePackage
from ..libs.pum import ParameterDefinition
from .parameters_groupbox import ParametersGroupBox

logger = logging.getLogger(__name__)


class UpgradeDialog(QDialog):
    """Dialog for confirming module upgrade with parameter review/editing."""

    def __init__(
        self,
        module_package: ModulePackage,
        standard_params: list[ParameterDefinition],
        app_only_params: list[ParameterDefinition],
        target_version: str,
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
        layout.addWidget(self.__standard_groupbox)

        # App-only parameters (editable)
        self.__app_only_groupbox = ParametersGroupBox(self)
        self.__app_only_groupbox.setTitle(self.tr("Application parameters"))
        gb_layout = QVBoxLayout()
        gb_layout.setContentsMargins(3, 3, 3, 3)
        self.__app_only_groupbox.setLayout(gb_layout)
        self.__app_only_groupbox.setParameters(app_only_params)
        layout.addWidget(self.__app_only_groupbox)

        # Beta testing checkbox
        self.__beta_testing_checkbox = QCheckBox(self.tr("Beta testing"), self)
        self.__configure_beta_testing_checkbox(module_package)
        layout.addWidget(self.__beta_testing_checkbox)

        # Roles checkbox
        self.__roles_checkbox = QCheckBox(self.tr("Create and grant roles"), self)
        self.__roles_checkbox.setChecked(True)
        layout.addWidget(self.__roles_checkbox)

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
        return self.__roles_checkbox.isChecked()
