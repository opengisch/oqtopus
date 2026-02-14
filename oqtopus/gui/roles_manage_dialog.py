"""Dialog for managing database roles (check, create, grant)."""

import logging

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ..libs.pum.role_manager import RoleInventory, RoleManager
from .roles_create_dialog import RolesCreateDialog

logger = logging.getLogger(__name__)


_ROLE_STATUS_ROLE = Qt.ItemDataRole.UserRole
_GROUP_SUFFIX_ROLE = Qt.ItemDataRole.UserRole + 1  # suffix str stored on group headers
_LOGIN_ROLE_NAME = Qt.ItemDataRole.UserRole + 2  # str stored on login role items


class RolesManageDialog(QDialog):
    """Manage database roles: check status, create, grant, revoke, drop."""

    _OK = "\u2705"  # ✅
    _WARN = "\u26a0\ufe0f"  # ⚠️
    _MISS = "\u274c"  # ❌

    def __init__(
        self,
        result: RoleInventory,
        *,
        connection=None,
        role_manager: RoleManager | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._connection = connection
        self._role_manager = role_manager
        self.setWindowTitle(self.tr("Manage roles"))
        self.setMinimumSize(700, 400)
        self.resize(850, 500)

        layout = QVBoxLayout(self)

        # --- Summary ---
        self._summary_label = QLabel(self)
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        # --- Tree ---
        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabels(
            [
                self.tr("Role"),
                self.tr("Status"),
                self.tr("Login"),
                self.tr("Details"),
            ]
        )
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._tree)

        # --- Action buttons ---
        action_layout = QHBoxLayout()

        create_and_grant_roles_button = QPushButton(self.tr("Create and grant roles"), self)
        create_and_grant_roles_button.clicked.connect(self._on_create_grant_roles)
        action_layout.addWidget(create_and_grant_roles_button)

        create_login_role_button = QPushButton(self.tr("Create login role"), self)
        create_login_role_button.clicked.connect(self._on_create_login_role)
        action_layout.addWidget(create_login_role_button)

        action_layout.addStretch()
        layout.addLayout(action_layout)

        # --- Close button ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._populate(result)

    # ------------------------------------------------------------------
    # Populate / refresh
    # ------------------------------------------------------------------

    def _populate(self, result: RoleInventory):
        """Fill / refresh the summary label and tree from *result*."""
        # --- Summary ---
        parts: list[str] = []
        n_configured = len(result.configured_roles)
        n_missing = len(result.missing_roles)
        n_unknown = len(result.unknown_roles)
        n_login = len(result.other_login_roles)

        if n_missing:
            parts.append(self.tr("%n module role(s) missing", "", n_missing))
        bad_perms = [
            r
            for r in result.configured_roles
            if any(not sp.satisfied for sp in r.schema_permissions)
        ]
        if bad_perms:
            parts.append(self.tr("%n role(s) with wrong permissions", "", len(bad_perms)))

        if parts:
            self._summary_label.setText(", ".join(parts) + ".")
        else:
            if n_configured:
                summary = (
                    self.tr("%n module role(s)", "", n_configured)
                    + self.tr(", %n unknown role(s)", "", n_unknown)
                    + self.tr(", %n login role(s)", "", n_login)
                )
            else:
                summary = self.tr("No roles found.")
            self._summary_label.setText(summary)

        # --- Tree ---
        tree = self._tree
        tree.clear()

        # ==============================================================
        # 1) MODULE ROLES (configured generic + suffixed + missing)
        # ==============================================================
        generic_roles: list = []
        specific_by_suffix: dict[str, list] = {}
        for rs in result.configured_roles:
            if rs.is_suffixed:
                specific_by_suffix.setdefault(rs.suffix, []).append(rs)
            else:
                generic_roles.append(rs)

        # Generic roles whose DB role doesn't exist (even if suffixed variants do)
        found_generic_names = {rs.role.name for rs in generic_roles}
        missing_generic = [
            name for name in result.expected_roles if name not in found_generic_names
        ]

        has_module_roles = bool(generic_roles or missing_generic or specific_by_suffix)
        if has_module_roles:
            module_header = QTreeWidgetItem(tree, [self.tr("Module roles")])
            module_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._set_bold(module_header)

            # -- Generic sub-group --
            if generic_roles or missing_generic:
                generic_header = QTreeWidgetItem(module_header, [self.tr("Generic roles")])
                generic_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
                generic_header.setData(0, _GROUP_SUFFIX_ROLE, "")
                self._set_bold(generic_header)

                for rs in generic_roles:
                    self._add_role_item(generic_header, rs)
                for name in missing_generic:
                    QTreeWidgetItem(
                        generic_header,
                        [name, f"{self._MISS} {self.tr('missing')}", "", ""],
                    )
                generic_header.setExpanded(True)

            # -- Specific sub-groups --
            for suffix in sorted(specific_by_suffix):
                suffix_header = QTreeWidgetItem(
                    module_header, [self.tr("Specific roles (%s)") % suffix]
                )
                suffix_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
                suffix_header.setData(0, _GROUP_SUFFIX_ROLE, suffix)
                self._set_bold(suffix_header)

                for rs in specific_by_suffix[suffix]:
                    self._add_role_item(suffix_header, rs)

                found_config_names = {rs.role.name for rs in specific_by_suffix[suffix]}
                for name in result.expected_roles:
                    if name not in found_config_names:
                        suffixed_name = f"{name}_{suffix}"
                        QTreeWidgetItem(
                            suffix_header,
                            [suffixed_name, f"{self._MISS} {self.tr('missing')}", "", ""],
                        )
                suffix_header.setExpanded(True)

            module_header.setExpanded(True)

        # ==============================================================
        # 2) GRANTEE ROLES (login users granted membership in module roles)
        # ==============================================================
        if result.grantee_roles:
            grantee_header = QTreeWidgetItem(tree, [self.tr("Grantee roles")])
            grantee_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._set_bold(grantee_header)

            for rs in result.grantee_roles:
                member_of = ", ".join(rs.granted_to)
                login_text = self.tr("yes") if rs.login else self.tr("no")
                item = QTreeWidgetItem(
                    grantee_header,
                    [rs.name, self._OK, login_text, self.tr("member of: %s") % member_of],
                )
                item.setData(0, _LOGIN_ROLE_NAME, rs.name)
            grantee_header.setExpanded(True)

        # ==============================================================
        # 3) UNKNOWN ROLES (schema access but not configured or grantees)
        # ==============================================================
        if result.unknown_roles:
            unknown_header = QTreeWidgetItem(tree, [self.tr("Unknown roles")])
            unknown_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._set_bold(unknown_header)

            for rs in result.unknown_roles:
                schemas_str = ", ".join(rs.schemas)
                detail = self.tr("schemas: %s") % schemas_str
                if rs.superuser:
                    detail = self.tr("superuser") + " \u2014 " + detail
                login_text = self.tr("yes") if rs.login else self.tr("no")
                QTreeWidgetItem(
                    unknown_header,
                    [rs.name, self._WARN, login_text, detail],
                )
            unknown_header.setExpanded(True)

        # ==============================================================
        # 4) LOGIN ROLES (candidates — no schema access)
        # ==============================================================
        if result.other_login_roles:
            login_header = QTreeWidgetItem(tree, [self.tr("Login roles")])
            login_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._set_bold(login_header)

            for name in result.other_login_roles:
                item = QTreeWidgetItem(
                    login_header,
                    [name, "", self.tr("yes"), ""],
                )
                item.setData(0, _LOGIN_ROLE_NAME, name)
            login_header.setExpanded(True)

        # Resize columns
        for col in range(tree.columnCount()):
            tree.header().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

    def _refresh(self):
        """Re-run roles_inventory and repopulate the dialog."""
        if not self._connection or not self._role_manager:
            return
        try:
            with self._connection.transaction():
                result = self._role_manager.roles_inventory(
                    connection=self._connection, include_superusers=True
                )
            self._populate(result)
        except Exception as exc:
            logger.error(f"Failed to refresh roles: {exc}")

    # ------------------------------------------------------------------
    # Action buttons
    # ------------------------------------------------------------------

    def _on_create_grant_roles(self):
        """Show the RolesCreateDialog and create/grant roles."""
        if not self._connection or not self._role_manager:
            return

        dialog = RolesCreateDialog(self)
        if dialog.exec() != RolesCreateDialog.DialogCode.Accepted:
            return

        options = dialog.roles_options()
        suffix = options.get("suffix")

        try:
            self._role_manager.create_roles(
                connection=self._connection,
                suffix=suffix,
                grant=True,
                commit=True,
            )
            QMessageBox.information(
                self,
                self.tr("Create and grant roles"),
                self.tr("Roles created and granted successfully."),
            )
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Failed to create roles: %s") % exc,
            )

    def _on_create_login_role(self):
        """Prompt for a name and password, then create a LOGIN role."""
        if not self._connection:
            return

        name, ok = QInputDialog.getText(
            self,
            self.tr("Create login role"),
            self.tr("Role name:"),
        )
        if not ok or not name.strip():
            return

        password, ok = QInputDialog.getText(
            self,
            self.tr("Create login role"),
            self.tr("Password (leave empty for no password):"),
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return

        name = name.strip()
        password = password.strip() or None
        try:
            RoleManager.create_login_role(self._connection, name, password=password, commit=True)
            QMessageBox.information(
                self,
                self.tr("Create login role"),
                self.tr("Login role '%s' created.") % name,
            )
            self._refresh()
        except Exception as exc:
            self._connection.rollback()
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Failed to create login role: %s") % exc,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_role_item(self, parent: QTreeWidgetItem, rs) -> QTreeWidgetItem:
        """Add a single role row under *parent*."""
        all_ok = all(sp.satisfied for sp in rs.schema_permissions)
        icon = self._OK if all_ok else self._WARN
        status_text = self.tr("ok") if all_ok else self.tr("permissions mismatch")
        login_text = self.tr("yes") if rs.login else self.tr("no")
        summary, tooltip = self._build_details(rs)
        item = QTreeWidgetItem(
            parent,
            [rs.name, f"{icon} {status_text}", login_text, summary],
        )
        if tooltip:
            item.setToolTip(3, tooltip)
        item.setData(0, _ROLE_STATUS_ROLE, rs)
        return item

    def _build_details(self, rs) -> tuple[str, str]:
        """Build a short summary and an HTML tooltip for a configured role.

        Returns:
            A tuple of (summary_text, html_tooltip).
        """
        # -- Summary (plain text, shown in the column) --
        schema_names = [sp.schema for sp in rs.schema_permissions]
        summary_parts: list[str] = []
        if schema_names:
            summary_parts.append(", ".join(schema_names))
        if rs.granted_to:
            summary_parts.append(self.tr("member of %s") % ", ".join(rs.granted_to))
        summary = " \u2014 ".join(summary_parts)

        # -- Tooltip (HTML, shown on hover) --
        lines: list[str] = []
        if rs.schema_permissions:
            lines.append(f"<b>{self.tr('Schemas')}</b>")
            for sp in rs.schema_permissions:
                expected = sp.expected.name.upper() if sp.expected else "\u2014"
                actual_bits: list[str] = []
                if sp.has_read:
                    actual_bits.append("READ")
                if sp.has_write:
                    actual_bits.append("WRITE")
                actual = ", ".join(actual_bits) if actual_bits else self.tr("none")
                if sp.satisfied:
                    lines.append(f"&nbsp;&nbsp;\u2022 {sp.schema}: {expected}")
                else:
                    lines.append(
                        f"&nbsp;&nbsp;\u2022 {sp.schema}: "
                        f"<span style='color:orange'>{actual}</span> "
                        f"(expected {expected})"
                    )
        if rs.granted_to:
            lines.append(f"<b>{self.tr('Member of')}</b>")
            for g in rs.granted_to:
                lines.append(f"&nbsp;&nbsp;\u2022 {g}")

        tooltip = "<br>".join(lines) if lines else ""
        return summary, tooltip

    @staticmethod
    def _set_bold(item: QTreeWidgetItem):
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _on_context_menu(self, pos):
        """Show context menu for a role item or group header."""
        if not self._connection or not self._role_manager:
            return

        item = self._tree.itemAt(pos)
        if item is None:
            return

        rs = item.data(0, _ROLE_STATUS_ROLE)
        group_suffix = item.data(0, _GROUP_SUFFIX_ROLE)
        login_name = item.data(0, _LOGIN_ROLE_NAME)

        if rs is not None:
            # Individual role item
            self._show_role_menu(rs)
        elif group_suffix is not None:
            # Group header (generic or specific)
            self._show_group_menu(group_suffix)
        elif login_name is not None:
            # Login role item
            self._show_login_role_menu(login_name)

    def _show_role_menu(self, rs):
        """Context menu for a single role."""
        config_roles = [rs.role.name] if rs.role else None
        suffix = rs.suffix if rs.is_suffixed else None
        db_role_name = rs.name  # actual PG role name

        menu = QMenu(self)

        # -- Grant to submenu --
        login_roles = self._fetch_login_roles()
        if login_roles:
            grant_menu = menu.addMenu(self.tr("Grant to"))
            for user in login_roles:
                action = grant_menu.addAction(user)
                action.setData(("grant_to", user, config_roles, suffix, db_role_name))

        # -- Revoke from submenu (only users that are members) --
        members = self._fetch_members_of(db_role_name)
        if members:
            revoke_from_menu = menu.addMenu(self.tr("Revoke from"))
            for user in members:
                action = revoke_from_menu.addAction(user)
                action.setData(("revoke_from", user, config_roles, suffix, db_role_name))

        menu.addSeparator()
        revoke_action = menu.addAction(self.tr("Revoke permissions"))
        drop_action = menu.addAction(self.tr("Drop role"))

        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return

        data = chosen.data()
        if isinstance(data, tuple):
            action_type, user, roles, sfx, label = data
            if action_type == "grant_to":
                self._grant_to(to=user, roles=roles, suffix=sfx, label=label)
            elif action_type == "revoke_from":
                self._revoke_from(from_role=user, roles=roles, suffix=sfx, label=label)
        elif chosen is revoke_action:
            self._revoke_roles(
                roles=config_roles,
                suffix=suffix,
                label=db_role_name,
            )
        elif chosen is drop_action:
            self._drop_roles(
                roles=config_roles,
                suffix=suffix,
                label=db_role_name,
            )

    def _show_group_menu(self, group_suffix: str):
        """Context menu for a group header (all roles in group)."""
        suffix = group_suffix or None  # "" → None (generic group)
        kind = (
            self.tr("specific roles (%s)") % group_suffix if suffix else self.tr("generic roles")
        )

        menu = QMenu(self)

        # -- Grant all to submenu --
        login_roles = self._fetch_login_roles()
        if login_roles:
            grant_menu = menu.addMenu(self.tr("Grant all to"))
            for user in login_roles:
                action = grant_menu.addAction(user)
                action.setData(("grant_to", user, None, suffix, kind))

        menu.addSeparator()
        revoke_action = menu.addAction(self.tr("Revoke all permissions"))
        drop_action = menu.addAction(self.tr("Drop all roles"))

        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return

        data = chosen.data()
        if isinstance(data, tuple):
            action_type, user, roles, sfx, label = data
            if action_type == "grant_to":
                self._grant_to(to=user, roles=roles, suffix=sfx, label=label)
        elif chosen is revoke_action:
            self._revoke_roles(roles=None, suffix=suffix, label=kind)
        elif chosen is drop_action:
            self._drop_roles(roles=None, suffix=suffix, label=kind)

    def _show_login_role_menu(self, name: str):
        """Context menu for a login role item."""
        menu = QMenu(self)
        drop_action = menu.addAction(self.tr("Drop role"))

        chosen = menu.exec(QCursor.pos())
        if chosen is drop_action:
            self._drop_login_role(name)

    # ------------------------------------------------------------------
    # Grant / Revoke membership
    # ------------------------------------------------------------------

    def _fetch_login_roles(self) -> list[str]:
        """Return login role names excluding module roles and superusers."""
        if not self._connection or not self._role_manager:
            return []

        try:
            exclude = set(self._role_manager.roles.keys())
            return [
                name for name in RoleManager.login_roles(self._connection) if name not in exclude
            ]
        except Exception as exc:
            logger.error(f"Failed to fetch login roles: {exc}")
            return []

    def _fetch_members_of(self, role_name: str) -> list[str]:
        """Return login role names that are members of *role_name*."""
        if not self._connection:
            return []
        try:
            return RoleManager.members_of(self._connection, role_name)
        except Exception as exc:
            logger.error(f"Failed to fetch members of {role_name}: {exc}")
            return []

    def _grant_to(self, *, to: str, roles: list[str] | None, suffix: str | None, label: str):
        """Grant a role (or all roles) to a login user."""
        answer = QMessageBox.question(
            self,
            self.tr("Grant role"),
            self.tr("Grant %s to %s?") % (label, to),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._role_manager.grant_to(
                connection=self._connection,
                to=to,
                roles=roles,
                suffix=suffix,
                commit=True,
            )
            QMessageBox.information(
                self,
                self.tr("Grant role"),
                self.tr("%s granted to %s.") % (label, to),
            )
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Failed to grant role: %s") % exc,
            )

    def _revoke_from(
        self, *, from_role: str, roles: list[str] | None, suffix: str | None, label: str
    ):
        """Revoke a role (or all roles) from a login user."""
        answer = QMessageBox.question(
            self,
            self.tr("Revoke role"),
            self.tr("Revoke %s from %s?") % (label, from_role),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._role_manager.revoke_from(
                connection=self._connection,
                from_role=from_role,
                roles=roles,
                suffix=suffix,
                commit=True,
            )
            QMessageBox.information(
                self,
                self.tr("Revoke role"),
                self.tr("%s revoked from %s.") % (label, from_role),
            )
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Failed to revoke role: %s") % exc,
            )

    # ------------------------------------------------------------------
    # Revoke permissions / Drop
    # ------------------------------------------------------------------

    def _revoke_roles(self, *, roles: list[str] | None, suffix: str | None, label: str):
        """Revoke permissions from one or all roles."""
        answer = QMessageBox.question(
            self,
            self.tr("Revoke permissions"),
            self.tr("Revoke permissions from %s?") % label,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._role_manager.revoke_permissions(
                connection=self._connection,
                roles=roles,
                suffix=suffix,
                commit=True,
            )
            QMessageBox.information(
                self,
                self.tr("Revoke permissions"),
                self.tr("Permissions revoked from %s.") % label,
            )
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Failed to revoke permissions: %s") % exc,
            )

    def _drop_roles(self, *, roles: list[str] | None, suffix: str | None, label: str):
        """Drop one or all roles (revokes permissions first)."""
        answer = QMessageBox.question(
            self,
            self.tr("Drop role"),
            self.tr("Drop %s? This will also revoke permissions.") % label,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._role_manager.drop_roles(
                connection=self._connection,
                roles=roles,
                suffix=suffix,
                commit=True,
            )
            QMessageBox.information(
                self,
                self.tr("Drop role"),
                self.tr("%s dropped.") % label,
            )
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Failed to drop role: %s") % exc,
            )

    def _drop_login_role(self, name: str):
        """Drop a login role."""
        answer = QMessageBox.question(
            self,
            self.tr("Drop login role"),
            self.tr("Drop login role '%s'?") % name,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            RoleManager.drop_login_role(self._connection, name, commit=True)
            QMessageBox.information(
                self,
                self.tr("Drop login role"),
                self.tr("Login role '%s' dropped.") % name,
            )
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Failed to drop login role: %s") % exc,
            )
