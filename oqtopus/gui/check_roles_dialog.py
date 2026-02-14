"""Dialog displaying the results of a role check."""

import logging

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ..libs.pum.role_manager import RoleCheckResult

logger = logging.getLogger(__name__)


class CheckRolesDialog(QDialog):
    """Display the result of ``RoleManager.check_roles()``."""

    # Icons as simple text markers (works without resource files).
    _OK = "\u2705"  # ✅
    _WARN = "\u26a0\ufe0f"  # ⚠️
    _MISS = "\u274c"  # ❌

    def __init__(self, result: RoleCheckResult, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Check roles"))
        self.setMinimumSize(600, 400)
        self.resize(700, 500)

        layout = QVBoxLayout(self)

        # --- Summary label ---
        if result.ok:
            summary = self.tr("All defined roles are present with the expected permissions.")
        else:
            problems: list[str] = []
            missing = [r for r in result.roles if not r.exists]
            bad_perms = [r for r in result.roles if r.exists and not r.ok]
            if missing:
                problems.append(self.tr("%n role(s) missing", "", len(missing)))
            if bad_perms:
                problems.append(self.tr("%n role(s) with wrong permissions", "", len(bad_perms)))
            if result.unknown_roles:
                problems.append(self.tr("%n unknown role(s)", "", len(result.unknown_roles)))
            summary = ", ".join(problems) + "."

        summary_label = QLabel(summary, self)
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        # --- Tree ---
        tree = QTreeWidget(self)
        tree.setHeaderLabels([self.tr("Role / Schema"), self.tr("Status"), self.tr("Details")])
        tree.setRootIsDecorated(True)
        tree.setAlternatingRowColors(True)

        # -- Defined roles --
        defined_header = QTreeWidgetItem(tree, [self.tr("Defined roles")])
        defined_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font = defined_header.font(0)
        font.setBold(True)
        defined_header.setFont(0, font)

        for role_status in result.roles:
            if role_status.exists:
                icon = self._OK if role_status.ok else self._WARN
                status_text = self.tr("exists")
            else:
                icon = self._MISS
                status_text = self.tr("missing")

            role_item = QTreeWidgetItem(
                defined_header, [role_status.name, f"{icon} {status_text}"]
            )

            for sp in role_status.schema_permissions:
                perm_icon = self._OK if sp.ok else self._MISS
                expected = sp.expected.name if sp.expected else "—"
                actual_parts: list[str] = []
                if sp.has_read:
                    actual_parts.append("read")
                if sp.has_write:
                    actual_parts.append("write")
                actual = ", ".join(actual_parts) if actual_parts else self.tr("none")
                QTreeWidgetItem(
                    role_item,
                    [sp.schema, f"{perm_icon} {expected}", self.tr("has: %s") % actual],
                )

        defined_header.setExpanded(True)

        # -- Unknown roles --
        if result.unknown_roles:
            unknown_header = QTreeWidgetItem(tree, [self.tr("Unknown roles")])
            unknown_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = unknown_header.font(0)
            font.setBold(True)
            unknown_header.setFont(0, font)

            for unknown in result.unknown_roles:
                schemas_str = ", ".join(unknown.schemas)
                QTreeWidgetItem(
                    unknown_header,
                    [unknown.name, self._WARN, self.tr("schemas: %s") % schemas_str],
                )

            unknown_header.setExpanded(True)

        # Resize columns to content
        for col in range(tree.columnCount()):
            tree.header().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(tree)

        # --- Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
