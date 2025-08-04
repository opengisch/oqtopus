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
from pgserviceparser import full_config as pgserviceparser_full_config
from pgserviceparser import service_config as pgserviceparser_service_config
from pgserviceparser import write_service as pgserviceparser_write_service
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import OverrideCursor

DIALOG_UI = PluginUtils.get_ui_class("database_duplicate_dialog.ui")


class DatabaseDuplicateDialog(QDialog, DIALOG_UI):
    def __init__(self, selected_service=None, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        self.existingService_label.setText(selected_service)

        self.__existing_service_config = pgserviceparser_service_config(selected_service)
        self.existingDatabase_label.setText(self.__existing_service_config.get("dbname", ""))

        self.buttonBox.accepted.connect(self._accept)

    def _accept(self):

        if self.newDatabase_lineEdit.text() == "":
            QMessageBox.critical(self, "Error", "Please enter a database name.")
            return

        if self.newService_lineEdit.text() == "":
            QMessageBox.critical(self, "Error", "Please enter a service name.")
            return

        service_name = self.existingService_label.text()
        try:
            database_connection = psycopg.connect(service=service_name)

        except Exception as exception:
            errorText = self.tr(f"Can't connect to service '{service_name}':\n{exception}.")
            logger.error(errorText)
            QMessageBox.critical(self, "Error", errorText)
            return

        # Create new service configuration
        new_service_name = self.newService_lineEdit.text()

        # Check if the new service name is already in use
        try:
            if new_service_name in pgserviceparser_full_config():
                errorText = self.tr(f"Service name '{new_service_name}' is already in use.")
                logger.error(errorText)
                QMessageBox.critical(self, "Error", errorText)
                return
        except Exception as e:
            errorText = self.tr(f"Error checking existing service names:\n{e}.")
            logger.error(errorText)
            QMessageBox.critical(self, "Error", errorText)
            return

        # Duplicate the database
        new_database_name = self.newDatabase_lineEdit.text()
        try:
            database_connection.autocommit = True
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                with database_connection.cursor() as cursor:
                    cursor.execute(
                        f"CREATE DATABASE {new_database_name} TEMPLATE {self.__existing_service_config.get('dbname')}"
                    )
        except psycopg.Error as e:
            errorText = self.tr(f"Error duplicating database:\n{e}.")
            logger.error(errorText)
            QMessageBox.critical(self, "Error", errorText)
            return
        finally:
            database_connection.close()

        # Write the new service configuration
        try:
            new_service_config = {
                "dbname": new_database_name,
                "host": self.__existing_service_config.get("host", ""),
                "port": self.__existing_service_config.get("port", ""),
                "user": self.__existing_service_config.get("user", ""),
                "password": self.__existing_service_config.get("password", ""),
            }
            pgserviceparser_write_service(
                new_service_name, new_service_config, create_if_not_found=True
            )
        except Exception as e:
            errorText = self.tr(f"Error writing new service configuration:\n{e}.")
            logger.error(errorText)
            QMessageBox.critical(self, "Error", errorText)
            return

        super().accept()
