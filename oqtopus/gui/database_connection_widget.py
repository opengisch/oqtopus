import psycopg
from pgserviceparser import conf_path as pgserviceparser_conf_path
from pgserviceparser import service_config as pgserviceparser_service_config
from pgserviceparser import service_names as pgserviceparser_service_names
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QAction
from qgis.PyQt.QtWidgets import QDialog, QMenu, QWidget

from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import CriticalMessageBox, QtUtils
from .database_create_dialog import DatabaseCreateDialog
from .database_duplicate_dialog import DatabaseDuplicateDialog

DIALOG_UI = PluginUtils.get_ui_class("database_connection_widget.ui")


class DatabaseConnectionWidget(QWidget, DIALOG_UI):

    signal_connectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)

        self.db_database_label.setText(self.tr("No database"))
        QtUtils.setForegroundColor(self.db_database_label, PluginUtils.COLOR_WARNING)
        QtUtils.setFontItalic(self.db_database_label, True)

        self.__loadDatabaseInformations()
        self.db_services_comboBox.currentIndexChanged.connect(self.__serviceChanged)

        db_operations_menu = QMenu(self.db_operations_toolButton)

        actionCreateDb = QAction(self.tr("Create database"), db_operations_menu)
        self.__actionDuplicateDb = QAction(self.tr("Duplicate database"), db_operations_menu)
        actionReloadPgServices = QAction(self.tr("Reload PG Service config"), db_operations_menu)

        actionCreateDb.triggered.connect(self.__createDatabaseClicked)
        self.__actionDuplicateDb.triggered.connect(self.__duplicateDatabaseClicked)
        actionReloadPgServices.triggered.connect(self.__loadDatabaseInformations)

        db_operations_menu.addAction(actionCreateDb)
        db_operations_menu.addAction(self.__actionDuplicateDb)
        db_operations_menu.addAction(actionReloadPgServices)

        self.db_operations_toolButton.setMenu(db_operations_menu)

        self.__database_connection = None

        try:
            self.__serviceChanged()
        except Exception:
            # Silence errors during widget initialization
            pass

    def getConnection(self):
        """
        Returns the current database connection.
        If no connection is established, returns None.
        """
        return self.__database_connection

    def getService(self):
        """
        Returns the current service name.
        If no service is selected, returns None.
        """
        if self.db_services_comboBox.currentText() == "":
            return None
        return self.db_services_comboBox.currentText()

    def __loadDatabaseInformations(self):
        pg_service_conf_path = pgserviceparser_conf_path()
        self.db_servicesConfigFilePath_label.setText(
            f"<a href='file://{pg_service_conf_path.resolve()}'>{pg_service_conf_path.as_posix()}</a>"
        )

        self.db_services_comboBox.clear()

        try:
            for service_name in pgserviceparser_service_names():
                self.db_services_comboBox.addItem(service_name)
        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't load database services:"), exception, self
            ).exec()
            return

    def __serviceChanged(self, index=None):
        if self.db_services_comboBox.currentText() == "":
            self.db_database_label.setText(self.tr("No database"))
            QtUtils.setForegroundColor(self.db_database_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.db_database_label, True)

            self.__actionDuplicateDb.setDisabled(True)

            self.__set_connection(None)
            return

        service_name = self.db_services_comboBox.currentText()
        service_config = pgserviceparser_service_config(service_name)

        service_database = service_config.get("dbname", None)

        if service_database is None:
            self.db_database_label.setText(self.tr("No database provided by the service"))
            QtUtils.setForegroundColor(self.db_database_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.db_database_label, True)

            self.__actionDuplicateDb.setDisabled(True)
            return

        self.db_database_label.setText(service_database)
        QtUtils.resetForegroundColor(self.db_database_label)
        QtUtils.setFontItalic(self.db_database_label, False)

        self.__actionDuplicateDb.setEnabled(True)

        # Try connection
        try:
            database_connection = psycopg.connect(service=service_name)
            self.__set_connection(database_connection)

        except Exception as exception:
            self.__set_connection(None)

            self.db_moduleInfo_label.setText("Can't connect to service.")
            QtUtils.setForegroundColor(self.db_moduleInfo_label, PluginUtils.COLOR_WARNING)
            errorText = self.tr(f"Can't connect to service '{service_name}':\n{exception}.")
            logger.error(errorText)
            return

        self.db_moduleInfo_label.setText("Connected.")
        logger.info(f"Connected to service '{service_name}'.")
        QtUtils.resetForegroundColor(self.db_moduleInfo_label)

    def __createDatabaseClicked(self):
        databaseCreateDialog = DatabaseCreateDialog(
            selected_service=self.db_services_comboBox.currentText(), parent=self
        )

        if databaseCreateDialog.exec() == QDialog.DialogCode.Rejected:
            return

        self.__loadDatabaseInformations()

        # Select the created service
        created_service_name = databaseCreateDialog.created_service_name()
        self.db_services_comboBox.setCurrentText(created_service_name)

    def __duplicateDatabaseClicked(self):
        databaseDuplicateDialog = DatabaseDuplicateDialog(
            selected_service=self.db_services_comboBox.currentText(), parent=self
        )

        # Close the current connection otherwise it will block the database duplication
        if self.__database_connection is not None:
            self.__database_connection.close()
            self.__database_connection = None

        if databaseDuplicateDialog.exec() == QDialog.DialogCode.Rejected:
            self.__serviceChanged()
            return

        self.__loadDatabaseInformations()

    def __set_connection(self, connection):
        """
        Set the current database connection and emit the signal_connectionChanged signal.
        """
        self.__database_connection = connection
        self.signal_connectionChanged.emit()
