import logging

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)

from ..libs.pum import ParameterDefinition
from .parameters_groupbox import ParametersGroupBox

logger = logging.getLogger(__name__)


class RecreateAppDialog(QDialog):
    """Dialog for confirming app recreation with parameter review/editing."""

    def __init__(
        self,
        standard_params: list[ParameterDefinition],
        app_only_params: list[ParameterDefinition],
        installed_parameters: dict | None = None,
        suffixes: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("(Re)create app"))
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Description
        description = QLabel(
            self.tr(
                "Are you sure you want to recreate the application?\n\n"
                "This will first drop the app and then create it again, "
                "executing the corresponding handlers."
            ),
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Standard parameters (read-only)
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

        # Generic roles are re-granted silently. Suffixed roles are DB-specific,
        # so let the user confirm which ones to re-grant.
        self.__suffix_checkboxes = {}
        if suffixes:
            self.__roles_groupbox = QGroupBox(self.tr("Re-grant permissions"), self)
            self.__roles_groupbox.setCheckable(True)
            self.__roles_groupbox.setChecked(True)
            roles_layout = QVBoxLayout(self.__roles_groupbox)
            roles_layout.setContentsMargins(6, 6, 6, 6)
            for suffix in suffixes:
                checkbox = QCheckBox(suffix, self.__roles_groupbox)
                checkbox.setChecked(True)
                roles_layout.addWidget(checkbox)
                self.__suffix_checkboxes[suffix] = checkbox
            layout.addWidget(self.__roles_groupbox)
        else:
            self.__roles_groupbox = None

        # Add stretch to push buttons to the bottom
        layout.addStretch()

        # OK / Cancel buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def parameters(self) -> dict:
        """Return combined parameter values from both groupboxes."""
        values = {}
        values.update(self.__standard_groupbox.parameters_values())
        values.update(self.__app_only_groupbox.parameters_values())
        return values

    def grant_options(self) -> dict:
        """Return a dict suitable for the recreate app operation options.

        Keys:
            grant (bool): Whether permissions should be re-granted.
            suffixes (list[str]): Suffixes of the DB-specific roles to re-grant.
                Empty means the generic roles.
        """
        if self.__roles_groupbox is None:
            return {"grant": True, "suffixes": []}

        if not self.__roles_groupbox.isChecked():
            return {"grant": False, "suffixes": []}

        suffixes = [
            suffix for suffix, checkbox in self.__suffix_checkboxes.items() if checkbox.isChecked()
        ]
        return {"grant": bool(suffixes), "suffixes": suffixes}
