"""Dialog for managing database roles (check, create, grant)."""

import logging

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ..libs.pgserviceparser.gui.message_bar import MessageBar
from ..libs.pum.role_manager import RoleInventory, RoleManager
from .database_access_dialog import DatabaseAccessDialog
from .roles_create_dialog import RolesCreateDialog

logger = logging.getLogger(__name__)


_ROLE_STATUS_ROLE = Qt.ItemDataRole.UserRole
_GROUP_SUFFIX_ROLE = Qt.ItemDataRole.UserRole + 1  # suffix str stored on group headers
_USER_NAME = Qt.ItemDataRole.UserRole + 2  # str stored on user items


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
        self.setWindowTitle(self.tr("Manage roles and users"))
        self.setMinimumSize(700, 400)
        self.resize(850, 500)

        layout = QVBoxLayout(self)

        # --- Message bar ---
        self._message_bar = MessageBar(self)
        layout.addWidget(self._message_bar)

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

        create_login_role_button = QPushButton(self.tr("Create user"), self)
        create_login_role_button.clicked.connect(self._on_create_login_role)
        action_layout.addWidget(create_login_role_button)

        self._configure_access_button = QPushButton(self.tr("Configure database access"), self)
        self._configure_access_button.setToolTip(
            self.tr(
                "Manage CONNECT privileges on this database.\n"
                "Control which roles are allowed to connect."
            )
        )
        self._configure_access_button.clicked.connect(self._on_configure_database_access)
        action_layout.addWidget(self._configure_access_button)

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
        self._last_inventory = result
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
                    + self.tr(", %n user(s)", "", n_login)
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
        # 2) GRANTEE ROLES (users granted membership in module roles)
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
                item.setData(0, _USER_NAME, rs.name)
            grantee_header.setExpanded(True)

        # ==============================================================
        # 3) USERS (candidates — no schema access)
        # ==============================================================
        if result.other_login_roles:
            users_header = QTreeWidgetItem(tree, [self.tr("Users")])
            users_header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._set_bold(users_header)

            for name in result.other_login_roles:
                item = QTreeWidgetItem(
                    users_header,
                    [name, "", self.tr("yes"), self.tr("no module role granted")],
                )
                item.setData(0, _USER_NAME, name)
            users_header.setExpanded(True)

        # ==============================================================
        # 4) UNKNOWN ROLES (schema access but not configured or grantees)
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

        # Resize columns
        for col in range(tree.columnCount()):
            tree.header().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

    def _refresh(self):
        """Re-run roles_inventory and repopulate the dialog."""
        if not self._connection or not self._role_manager:
            return
        try:
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
            self._message_bar.pushSuccess(self.tr("Roles created and granted successfully."))
            self._refresh()
        except Exception as exc:
            self._connection.rollback()
            self._message_bar.pushError(self.tr("Failed to create roles."), exception=exc)

    def _on_create_login_role(self):
        """Prompt for a name and optional password, then create a user (LOGIN role)."""
        if not self._connection:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Create user"))
        layout = QVBoxLayout(dlg)

        form = QFormLayout()
        name_edit = QLineEdit(dlg)
        form.addRow(self.tr("Role name:"), name_edit)

        password_check = QCheckBox(self.tr("Set password"), dlg)
        password_edit = QLineEdit(dlg)
        password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        password_edit.setEnabled(False)
        password_check.toggled.connect(password_edit.setEnabled)

        pw_layout = QHBoxLayout()
        pw_layout.addWidget(password_check)
        pw_layout.addWidget(password_edit)
        form.addRow("", pw_layout)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name = name_edit.text().strip()
        if not name:
            return

        password = password_edit.text().strip() if password_check.isChecked() else None
        password = password or None
        try:
            RoleManager.create_login_role(self._connection, name, password=password, commit=True)
            self._message_bar.pushSuccess(self.tr("User '%s' created.") % name)
            self._refresh()
        except Exception as exc:
            self._connection.rollback()
            self._message_bar.pushError(self.tr("Failed to create user."), exception=exc)

    def _on_configure_database_access(self):
        """Open dialog to manage CONNECT privileges on the database."""
        if not self._connection:
            return

        module_role_names = [rs.name for rs in self._last_inventory.configured_roles]

        try:
            dlg = DatabaseAccessDialog(
                connection=self._connection,
                module_role_names=module_role_names,
                parent=self,
            )
            dlg.exec()
        except Exception as exc:
            self._message_bar.pushError(self.tr("Failed to query database access."), exception=exc)

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
        user_name = item.data(0, _USER_NAME)

        if rs is not None:
            # Individual role item
            self._show_role_menu(rs)
        elif group_suffix is not None:
            # Group header (generic or specific)
            self._show_group_menu(group_suffix)
        elif user_name is not None:
            # User item
            self._show_user_menu(user_name)

    def _show_role_menu(self, rs):
        """Context menu for a single role."""
        config_roles = [rs.role.name] if rs.role else None
        suffix = rs.suffix if rs.is_suffixed else None
        db_role_name = rs.name  # actual PG role name

        menu = QMenu(self)

        # -- Grant to submenu --
        users = self._fetch_users()
        if users:
            grant_menu = menu.addMenu(self.tr("Grant to"))
            for user in users:
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
        users = self._fetch_users()
        if users:
            grant_menu = menu.addMenu(self.tr("Grant all to"))
            for user in users:
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

    def _show_user_menu(self, name: str):
        """Context menu for a user item."""
        menu = QMenu(self)

        # Collect existing module roles and check membership
        module_roles = self._collect_module_roles()
        user_memberships = self._fetch_role_memberships(name)

        # -- Grant role submenu (module roles the user is NOT yet a member of) --
        grantable = [
            (rs, db_name) for rs, db_name in module_roles if db_name not in user_memberships
        ]
        if grantable:
            grant_menu = menu.addMenu(self.tr("Grant role"))
            for rs, db_name in grantable:
                config_roles = [rs.role.name] if rs.role else None
                suffix = rs.suffix if rs.is_suffixed else None
                action = grant_menu.addAction(db_name)
                action.setData(("grant_to", name, config_roles, suffix, db_name))

        # -- Revoke role submenu (module roles the user IS a member of) --
        revocable = [(rs, db_name) for rs, db_name in module_roles if db_name in user_memberships]
        if revocable:
            revoke_menu = menu.addMenu(self.tr("Revoke role"))
            for rs, db_name in revocable:
                config_roles = [rs.role.name] if rs.role else None
                suffix = rs.suffix if rs.is_suffixed else None
                action = revoke_menu.addAction(db_name)
                action.setData(("revoke_from", name, config_roles, suffix, db_name))

        menu.addSeparator()
        drop_action = menu.addAction(self.tr("Drop user"))

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
        elif chosen is drop_action:
            self._drop_user(name)

    # ------------------------------------------------------------------
    # Grant / Revoke membership
    # ------------------------------------------------------------------

    def _collect_module_roles(self) -> list[tuple]:
        """Return a list of (rs, db_role_name) for all existing module roles in the tree."""
        result = []
        tree = self._tree
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            self._collect_roles_recursive(top, result)
        return result

    def _collect_roles_recursive(self, item: QTreeWidgetItem, result: list):
        """Recursively collect items that have _ROLE_STATUS_ROLE data."""
        rs = item.data(0, _ROLE_STATUS_ROLE)
        if rs is not None:
            result.append((rs, rs.name))
        for i in range(item.childCount()):
            self._collect_roles_recursive(item.child(i), result)

    def _fetch_role_memberships(self, user_name: str) -> set[str]:
        """Return the set of role names that *user_name* is a member of."""
        if not self._connection:
            return set()
        try:
            return set(RoleManager.memberships_of(self._connection, user_name))
        except Exception as exc:
            logger.error(f"Failed to fetch memberships of {user_name}: {exc}")
            return set()

    def _fetch_users(self) -> list[str]:
        """Return user names (roles with LOGIN privilege) excluding module roles and superusers."""
        if not self._connection or not self._role_manager:
            return []

        try:
            exclude = set(self._role_manager.roles.keys())
            return [
                name for name in RoleManager.login_roles(self._connection) if name not in exclude
            ]
        except Exception as exc:
            logger.error(f"Failed to fetch users: {exc}")
            return []

    def _fetch_members_of(self, role_name: str) -> list[str]:
        """Return user names that are members of *role_name*."""
        if not self._connection:
            return []
        try:
            return RoleManager.members_of(self._connection, role_name)
        except Exception as exc:
            logger.error(f"Failed to fetch members of {role_name}: {exc}")
            return []

    def _grant_to(self, *, to: str, roles: list[str] | None, suffix: str | None, label: str):
        """Grant a role (or all roles) to a user."""
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
            self._message_bar.pushSuccess(self.tr("%s granted to %s.") % (label, to))
            self._refresh()
        except Exception as exc:
            self._connection.rollback()
            self._message_bar.pushError(self.tr("Failed to grant role."), exception=exc)

    def _revoke_from(
        self, *, from_role: str, roles: list[str] | None, suffix: str | None, label: str
    ):
        """Revoke a role (or all roles) from a user."""
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
            self._message_bar.pushSuccess(self.tr("%s revoked from %s.") % (label, from_role))
            self._refresh()
        except Exception as exc:
            self._connection.rollback()
            self._message_bar.pushError(self.tr("Failed to revoke role."), exception=exc)

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
            self._message_bar.pushSuccess(self.tr("Permissions revoked from %s.") % label)
            self._refresh()
        except Exception as exc:
            self._connection.rollback()
            self._message_bar.pushError(self.tr("Failed to revoke permissions."), exception=exc)

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
            self._message_bar.pushSuccess(self.tr("%s dropped.") % label)
            self._refresh()
        except Exception as exc:
            self._connection.rollback()

            # Ask the user whether to force-drop by reassigning
            # owned objects to the current connection user.
            current_user = self._connection.execute("SELECT current_user").fetchone()[0]

            dlg = QDialog(self)
            dlg.setWindowTitle(self.tr("Drop role"))
            dlg.setMinimumWidth(500)
            layout = QVBoxLayout(dlg)

            layout.addWidget(
                QLabel(
                    self.tr(
                        "There are still dependent objects or privileges.\n"
                        "Do you want to reassign owned objects to '%s' "
                        "and force drop?"
                    )
                    % current_user
                )
            )

            details = QTextEdit(dlg)
            details.setReadOnly(True)
            details.setPlainText(str(exc))
            layout.addWidget(details)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No,
                dlg,
            )
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)

            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            try:
                self._role_manager.drop_roles(
                    connection=self._connection,
                    roles=roles,
                    suffix=suffix,
                    force=True,
                    commit=True,
                )
                self._message_bar.pushSuccess(self.tr("%s dropped.") % label)
                self._refresh()
            except Exception as exc2:
                self._connection.rollback()
                self._message_bar.pushError(self.tr("Failed to drop role."), exception=exc2)

    def _drop_user(self, name: str):
        """Drop a user (a role with LOGIN privilege)."""
        answer = QMessageBox.question(
            self,
            self.tr("Drop user"),
            self.tr("Drop user '%s'?") % name,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            RoleManager.drop_login_role(self._connection, name, commit=True)
            self._message_bar.pushSuccess(self.tr("User '%s' dropped.") % name)
            self._refresh()
        except Exception as exc:
            self._connection.rollback()
            self._message_bar.pushError(self.tr("Failed to drop user."), exception=exc)
