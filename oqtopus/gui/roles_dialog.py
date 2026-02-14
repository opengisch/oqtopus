"""Dialog for configuring role creation options."""

import logging

from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from .roles_groupbox import RolesWidget

logger = logging.getLogger(__name__)


class RolesDialog(QDialog):
    """Dialog for choosing role creation options (specific / generic)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Create and grant roles"))
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        description = QLabel(
            self.tr("Configure the roles to create and grant for this module."),
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self._roles_widget = RolesWidget(self)
        layout.addWidget(self._roles_widget)

        layout.addStretch()

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setText(
            self.tr("Create roles")
        )
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        # Disable OK when nothing is selected
        self._roles_widget.selectionChanged.connect(self._update_ok_button)

    def _update_ok_button(self, has_selection: bool):
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(has_selection)

    def roles_options(self) -> dict:
        """Return the roles options dict."""
        return self._roles_widget.roles_options()
