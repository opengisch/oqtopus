# -----------------------------------------------------------
#
# Profile
# Copyright (C) 2025  Damiano Lombardi
# -----------------------------------------------------------
#
# licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, print to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# ---------------------------------------------------------------------

import psycopg
from pgserviceparser import service_config as pgserviceparser_service_config
from pgserviceparser import service_names as pgserviceparser_service_names
from pgserviceparser import write_service as pgserviceparser_write_service
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import OverrideCursor

DIALOG_UI = PluginUtils.get_ui_class("database_create_dialog.ui")


DEFAULT_PG_PORT = "5432"
DEFAULT_PG_DB = "postgres"
DEFAULT_PG_HOST = "localhost"


class DatabaseCreateDialog(QDialog, DIALOG_UI):
    def __init__(self, selected_service=None, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        self.existingService_comboBox.clear()
        for service_name in pgserviceparser_service_names():
            self.existingService_comboBox.addItem(service_name)

        if selected_service:
            self.existingService_comboBox.setCurrentText(selected_service)

        self.existingService_comboBox.currentIndexChanged.connect(self._serviceChanged)

        self.enterManually_radioButton.toggled.connect(self._enterManuallyToggled)

        self.parameters_ssl_comboBox.clear()
        self.parameters_ssl_comboBox.addItem("Not set", None)
        notSetFont = self.parameters_ssl_comboBox.font()
        notSetFont.setItalic(True)
        self.parameters_ssl_comboBox.setItemData(0, notSetFont, Qt.ItemDataRole.FontRole)
        self.parameters_ssl_comboBox.addItem("disable", "disable")
        self.parameters_ssl_comboBox.addItem("allow", "allow")
        self.parameters_ssl_comboBox.addItem("prefer", "prefer")
        self.parameters_ssl_comboBox.addItem("require", "require")
        self.parameters_ssl_comboBox.addItem("verify-ca", "verify-ca")
        self.parameters_ssl_comboBox.addItem("verify-full", "verify-full")
        self.parameters_ssl_comboBox.setCurrentIndex(2)  # Default to 'prefer'

        self.parameters_host_lineEdit.setPlaceholderText(DEFAULT_PG_HOST)
        self.parameters_port_lineEdit.setPlaceholderText(DEFAULT_PG_PORT)
        self.parameters_database_lineEdit.setPlaceholderText(DEFAULT_PG_DB)

        self.buttonBox.accepted.connect(self._accept)

        if self.existingService_comboBox.count() > 0:
            self._serviceChanged()

    def created_service_name(self):
        return self.service_lineEdit.text()

    def _serviceChanged(self):
        service_name = self.existingService_comboBox.currentText()
        service_config = pgserviceparser_service_config(service_name)

        service_host = service_config.get("host", None)
        service_port = service_config.get("port", None)
        service_ssl = service_config.get("sslmode", None)
        service_dbname = service_config.get("dbname", None)
        service_user = service_config.get("user", None)
        service_password = service_config.get("password", None)

        self.parameters_host_lineEdit.setText(service_host)
        self.parameters_port_lineEdit.setText(service_port)

        parameter_ssl_index = self.parameters_ssl_comboBox.findData(service_ssl)
        self.parameters_ssl_comboBox.setCurrentIndex(parameter_ssl_index)
        self.parameters_user_lineEdit.setText(service_user)
        self.parameters_password_lineEdit.setText(service_password)
        self.parameters_database_lineEdit.setText(service_dbname)

    def _enterManuallyToggled(self, checked):
        self.parameters_frame.setEnabled(checked)

    def _accept(self):
        service_name = self.created_service_name()

        if service_name == "":
            QMessageBox.critical(self, "Error", "Please enter a service name.")
            return

        # Check if the service name is already in use
        if service_name in pgserviceparser_service_names():
            QMessageBox.critical(
                self, "Error", self.tr(f"Service name '{service_name}' already exists.")
            )
            return

        new_database_name = self.database_lineEdit.text()
        if new_database_name == "":
            QMessageBox.critical(self, "Error", "Please enter a database name.")
            return

        database_connection = None
        try:
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                database_connection = psycopg.connect(**self._get_connection_parameters())
                database_connection.autocommit = True
                with database_connection.cursor() as cursor:
                    cursor.execute(
                        psycopg.sql.SQL("CREATE DATABASE {}").format(
                            psycopg.sql.Identifier(new_database_name)
                        )
                    )

        except Exception as e:
            errorText = self.tr(f"Error creating the new database:\n{e}.")
            logger.error(errorText)
            QMessageBox.critical(self, "Error", errorText)
            return

        finally:
            if database_connection:
                database_connection.close()

        # Proceed with writing the new service configuration
        service_settings = self._get_new_service_settings()

        try:
            pgserviceparser_write_service(
                service_name=service_name,
                settings=service_settings,
                create_if_not_found=True,
            )
        except Exception as e:
            errorText = self.tr(f"Error writing the new service configuration:\n{e}.")
            logger.error(errorText)
            QMessageBox.critical(self, "Error", errorText)
            return

        super().accept()

    def _get_connection_parameters(self):
        """
        Returns a dictionary of connection parameters suitable for psycopg.connect().
        Uses manual input if 'Enter manually' is checked, otherwise uses the selected service name.
        """
        settings = dict()
        if self.enterManually_radioButton.isChecked():
            settings.update(self._get_manual_connection_parameters())
        else:
            # Use the selected service name
            service_name = self.existingService_comboBox.currentText()
            if service_name:
                settings["service"] = service_name

        return settings

    def _get_new_service_settings(self):
        settings = dict()

        if self.enterManually_radioButton.isChecked():
            settings.update(self._get_manual_connection_parameters())
        else:
            # Copy settings from the selected existing service
            service_name = self.existingService_comboBox.currentText()
            existing_settings = pgserviceparser_service_config(service_name)
            settings.update(existing_settings)

        # Overwrite dbname with the new database name
        if self.database_lineEdit.text():
            settings["dbname"] = self.database_lineEdit.text()

        return settings

    def _get_manual_connection_parameters(self):
        parameters = dict()

        # Collect parameters from manual input fields
        if self.parameters_host_lineEdit.text():
            parameters["host"] = self.parameters_host_lineEdit.text() or DEFAULT_PG_HOST
        if self.parameters_port_lineEdit.text():
            parameters["port"] = self.parameters_port_lineEdit.text() or DEFAULT_PG_PORT
        if self.parameters_ssl_comboBox.currentData():
            parameters["sslmode"] = self.parameters_ssl_comboBox.currentData()
        if self.parameters_user_lineEdit.text():
            parameters["user"] = self.parameters_user_lineEdit.text()
        if self.parameters_password_lineEdit.text():
            parameters["password"] = self.parameters_password_lineEdit.text()
        if self.parameters_database_lineEdit.text():
            parameters["dbname"] = self.parameters_database_lineEdit.text() or DEFAULT_PG_DB

        return parameters
