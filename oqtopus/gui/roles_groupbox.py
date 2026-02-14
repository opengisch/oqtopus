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
    """Plain widget with generic / specific role checkboxes.

    Layout::

        [x] Create generic role(s)
        [ ] Create specific role(s) with suffix [________]
            [ ] Grant specific role(s) to generic role(s)

    The "Grant …" checkbox is only enabled when *both* specific and
    generic are checked, since it describes the relationship between
    the two.
    """

    selectionChanged = pyqtSignal(bool)  # emitted with has_selection()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Generic roles ---
        self._generic_checkbox = QCheckBox(self.tr("Create generic role(s)"), self)
        self._generic_checkbox.setChecked(True)
        layout.addWidget(self._generic_checkbox)

        # --- Specific roles row ---
        specific_layout = QHBoxLayout()
        self._specific_checkbox = QCheckBox(self.tr("Create specific role(s) with suffix"), self)
        self._specific_checkbox.setChecked(False)
        specific_layout.addWidget(self._specific_checkbox)

        self._suffix_edit = QLineEdit(self)
        self._suffix_edit.setPlaceholderText(self.tr("e.g. lausanne"))
        self._suffix_edit.setEnabled(False)
        specific_layout.addWidget(self._suffix_edit)
        layout.addLayout(specific_layout)

        # --- Grant specific → generic (relationship between the two) ---
        grant_layout = QHBoxLayout()
        grant_layout.setContentsMargins(20, 0, 0, 0)  # indent
        self._grant_checkbox = QCheckBox(
            self.tr("Grant specific role(s) to generic role(s)"), self
        )
        self._grant_checkbox.setChecked(False)
        self._grant_checkbox.setEnabled(False)
        grant_layout.addWidget(self._grant_checkbox)
        layout.addLayout(grant_layout)

        # --- Wiring ---
        self._generic_checkbox.toggled.connect(self._on_generic_toggled)
        self._specific_checkbox.toggled.connect(self._on_specific_toggled)
        self._suffix_edit.textChanged.connect(self._on_suffix_changed)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_generic_toggled(self, checked: bool):
        self._grant_checkbox.setEnabled(checked and self._specific_checkbox.isChecked())
        if not checked:
            self._grant_checkbox.setChecked(False)
        self.selectionChanged.emit(self.has_selection())

    def _on_specific_toggled(self, checked: bool):
        self._suffix_edit.setEnabled(checked)
        self._grant_checkbox.setEnabled(checked and self._generic_checkbox.isChecked())
        if not checked:
            self._grant_checkbox.setChecked(False)
        self.selectionChanged.emit(self.has_selection())

    def _on_suffix_changed(self):
        self.selectionChanged.emit(self.has_selection())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has_selection(self) -> bool:
        """Return True when the current selection is valid.

        Requires at least one role type to be selected, and if specific
        roles are checked, the suffix must be non-empty.
        """
        if self._specific_checkbox.isChecked() and not self._suffix_edit.text().strip():
            return False
        return self._generic_checkbox.isChecked() or self._specific_checkbox.isChecked()

    def roles_options(self) -> dict:
        """Return a dict suitable for ``create_roles()`` / upgrader options.

        Keys:
            roles (bool): Always True (the widget is shown only when roles
                are relevant).
            grant (bool): Always True.
            suffix (str | None): Suffix for specific roles, or None.
            create_generic (bool): Whether to create generic roles.
            grant_to_specific (bool): Whether to grant generic → specific.
        """
        suffix = self._suffix_edit.text().strip() if self._specific_checkbox.isChecked() else None
        if suffix == "":
            suffix = None

        return {
            "roles": True,
            "grant": True,
            "suffix": suffix,
            "create_generic": self._generic_checkbox.isChecked(),
            "grant_to_specific": self._grant_checkbox.isChecked(),
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
