"""Dialog for managing database CONNECT privileges."""

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

from ..libs.pgserviceparser.gui.message_bar import MessageBar
from ..libs.pum.database import (
    configure_database_connect_access,
    get_database_connect_access,
)

logger = logging.getLogger(__name__)

_ROLE_NAME = Qt.ItemDataRole.UserRole


class DatabaseAccessDialog(QDialog):
    """Manage CONNECT privileges on a PostgreSQL database."""

    def __init__(self, *, connection, module_role_names: list[str], parent=None):
        super().__init__(parent)
        self._connection = connection
        self._database_name = connection.info.dbname

        self.setWindowTitle(self.tr("Configure database access"))
        self.setMinimumSize(450, 300)

        layout = QVBoxLayout(self)

        # --- Message bar ---
        self._message_bar = MessageBar(self)
        layout.addWidget(self._message_bar)

        layout.addWidget(
            QLabel(self.tr("Manage CONNECT privilege on database '%s':") % self._database_name)
        )

        # --- Query current state ---
        public_connect, roles_with_connect = get_database_connect_access(
            connection, self._database_name
        )
        roles_connect_set = set(roles_with_connect)
        module_role_set = set(module_role_names)
        other_role_names = [r for r in roles_with_connect if r not in module_role_set]

        # --- Tree ---
        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabels([self.tr("Role"), self.tr("CONNECT")])
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        layout.addWidget(self._tree)

        self._checkable_flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsSelectable
        )
        self._disabled_flags = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable

        # -- PUBLIC --
        self._public_item = QTreeWidgetItem(self._tree, ["PUBLIC", ""])
        self._public_item.setFlags(self._checkable_flags)
        self._public_item.setCheckState(
            1, Qt.CheckState.Checked if public_connect else Qt.CheckState.Unchecked
        )
        self._public_item.setToolTip(
            0,
            self.tr(
                "PUBLIC is a special pseudo-role that represents all users.\n"
                "When CONNECT is granted to PUBLIC, any database user\n"
                "on this server can connect to this database.\n\n"
                "Uncheck to restrict access to specific roles only."
            ),
        )
        self._public_item.setData(0, _ROLE_NAME, "PUBLIC")

        # -- Module roles group --
        self._role_items: dict[str, QTreeWidgetItem] = {}
        if module_role_names:
            module_header = QTreeWidgetItem(self._tree, [self.tr("Module roles")])
            module_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = module_header.font(0)
            font.setBold(True)
            module_header.setFont(0, font)

            for name in module_role_names:
                item = QTreeWidgetItem(module_header, [name, ""])
                item.setFlags(self._checkable_flags)
                item.setCheckState(
                    1,
                    (
                        Qt.CheckState.Checked
                        if name in roles_connect_set
                        else Qt.CheckState.Unchecked
                    ),
                )
                item.setData(0, _ROLE_NAME, name)
                self._role_items[name] = item
            module_header.setExpanded(True)

        # -- Other roles group --
        if other_role_names:
            other_header = QTreeWidgetItem(self._tree, [self.tr("Other roles")])
            other_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = other_header.font(0)
            font.setBold(True)
            other_header.setFont(0, font)

            for name in other_role_names:
                item = QTreeWidgetItem(other_header, [name, ""])
                item.setFlags(self._checkable_flags)
                item.setCheckState(1, Qt.CheckState.Checked)
                item.setData(0, _ROLE_NAME, name)
                self._role_items[name] = item
            other_header.setExpanded(True)

        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        # Disable role checkboxes when PUBLIC is checked (they're redundant)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._update_role_items_enabled()

        # --- Buttons ---
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close,
            self,
        )
        btn_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        # Baseline state for computing diffs between applies
        self._state_public = public_connect
        self._state_roles = set(roles_connect_set)

    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """React to checkbox changes in the tree."""
        if item is self._public_item and column == 1:
            self._update_role_items_enabled()

    def _update_role_items_enabled(self):
        """Disable role checkboxes when PUBLIC has CONNECT (they're redundant)."""
        public_checked = self._public_item.checkState(1) == Qt.CheckState.Checked
        flags = self._disabled_flags if public_checked else self._checkable_flags
        for item in self._role_items.values():
            item.setFlags(flags)

    def _apply(self):
        """Compute diff and apply CONNECT changes."""
        new_public = self._public_item.checkState(1) == Qt.CheckState.Checked
        do_revoke_public = self._state_public and not new_public
        do_grant_public = not self._state_public and new_public

        grant_list = [
            n
            for n, item in self._role_items.items()
            if item.checkState(1) == Qt.CheckState.Checked and n not in self._state_roles
        ]
        revoke_list = [
            n
            for n, item in self._role_items.items()
            if item.checkState(1) != Qt.CheckState.Checked and n in self._state_roles
        ]

        if not any([do_revoke_public, do_grant_public, grant_list, revoke_list]):
            self._message_bar.pushWarning(self.tr("No changes to apply."))
            return

        if do_grant_public:
            public_action = True
        elif do_revoke_public:
            public_action = False
        else:
            public_action = None

        try:
            connection_params = {"conninfo": self._connection.info.dsn}
            configure_database_connect_access(
                connection_params,
                self._database_name,
                grant_roles=grant_list or None,
                revoke_roles=revoke_list or None,
                public=public_action,
            )
            self._message_bar.pushSuccess(self.tr("Database access updated."))
            # Update baseline for next apply
            self._state_public = new_public
            self._state_roles = {
                n
                for n, item in self._role_items.items()
                if item.checkState(1) == Qt.CheckState.Checked
            }
        except Exception as exc:
            self._message_bar.pushError(
                self.tr("Failed to configure database access."), exception=exc
            )
