"""Reusable widget and checkable groupbox for role creation options."""

import logging

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class RolesWidget(QWidget):
    """Plain widget with specific-role checkbox.

    Layout::

        [ ] Create specific role(s) with suffix [________]

    Generic roles are always created and granted.  When the checkbox is
    ticked, specific roles are also created (suffixed) and the generic
    roles receive membership of the specific ones.
    """

    selectionChanged = pyqtSignal(bool)  # emitted with has_selection()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Specific roles row ---
        specific_layout = QHBoxLayout()
        self._specific_checkbox = QCheckBox(self.tr("Create specific role(s) with suffix"), self)
        self._specific_checkbox.setChecked(False)
        self._specific_checkbox.setToolTip(
            self.tr(
                "Generic roles are always created and granted.\n"
                "Check this to also create specific (suffixed) roles\n"
                "and grant them to the generic roles."
            )
        )
        specific_layout.addWidget(self._specific_checkbox)

        self._suffix_edit = QLineEdit(self)
        self._suffix_edit.setPlaceholderText(self.tr("e.g. lausanne"))
        self._suffix_edit.setEnabled(False)
        specific_layout.addWidget(self._suffix_edit)
        layout.addLayout(specific_layout)

        # --- Wiring ---
        self._specific_checkbox.toggled.connect(self._on_specific_toggled)
        self._suffix_edit.textChanged.connect(self._on_suffix_changed)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_specific_toggled(self, checked: bool):
        self._suffix_edit.setEnabled(checked)
        self.selectionChanged.emit(self.has_selection())

    def _on_suffix_changed(self):
        self.selectionChanged.emit(self.has_selection())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has_selection(self) -> bool:
        """Return True when the current selection is valid.

        Always valid (generic roles are always created).  Only invalid
        when specific roles are checked but the suffix is empty.
        """
        if self._specific_checkbox.isChecked() and not self._suffix_edit.text().strip():
            return False
        return True

    def roles_options(self) -> dict:
        """Return a dict suitable for ``create_roles()`` / upgrader options.

        Keys:
            roles (bool): Always True (the widget is shown only when roles
                are relevant).
            grant (bool): Always True.
            suffix (str | None): Suffix for specific roles, or None.
        """
        suffix = self._suffix_edit.text().strip() if self._specific_checkbox.isChecked() else None
        if suffix == "":
            suffix = None

        return {
            "roles": True,
            "grant": True,
            "suffix": suffix,
        }


class RolesGroupBox(QGroupBox):
    """Checkable groupbox wrapping a :class:`RolesWidget`.

    Used inside InstallDialog / UpgradeDialog where roles can be
    toggled on or off entirely via the groupbox check.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle(self.tr("Roles"))
        self.setCheckable(True)
        self.setChecked(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._roles_widget = RolesWidget(self)
        layout.addWidget(self._roles_widget)

    def roles_options(self) -> dict:
        """Return a dict suitable for ``create_roles()`` / upgrader options."""
        if not self.isChecked():
            return {
                "roles": False,
                "grant": False,
            }
        return self._roles_widget.roles_options()
