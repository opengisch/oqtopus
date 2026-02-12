import logging

from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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
        layout.addWidget(self.__standard_groupbox)

        # App-only parameters (editable)
        self.__app_only_groupbox = ParametersGroupBox(self)
        self.__app_only_groupbox.setTitle(self.tr("Application parameters"))
        gb_layout = QVBoxLayout()
        gb_layout.setContentsMargins(3, 3, 3, 3)
        self.__app_only_groupbox.setLayout(gb_layout)
        self.__app_only_groupbox.setParameters(app_only_params)
        layout.addWidget(self.__app_only_groupbox)

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
