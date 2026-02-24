from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from ..libs.pgserviceparser import full_config as pgserviceparser_full_config
from ..libs.pgserviceparser import write_service as pgserviceparser_write_service
from ..utils.plugin_utils import PluginUtils, logger

DIALOG_UI = PluginUtils.get_ui_class("service_create_dialog.ui")


class ServiceCreateDialog(QDialog, DIALOG_UI):
    """Dialog to create a new PG service entry in pg_service.conf."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        self.__created_service_name = None

        self.sslmode_comboBox.clear()
        self.sslmode_comboBox.addItem(self.tr("Not set"), None)
        not_set_font = self.sslmode_comboBox.font()
        not_set_font.setItalic(True)
        self.sslmode_comboBox.setItemData(0, not_set_font, Qt.ItemDataRole.FontRole)
        self.sslmode_comboBox.addItem("disable", "disable")
        self.sslmode_comboBox.addItem("allow", "allow")
        self.sslmode_comboBox.addItem("prefer", "prefer")
        self.sslmode_comboBox.addItem("require", "require")
        self.sslmode_comboBox.addItem("verify-ca", "verify-ca")
        self.sslmode_comboBox.addItem("verify-full", "verify-full")
        self.sslmode_comboBox.setCurrentIndex(0)

        self.buttonBox.accepted.connect(self._accept)

    def created_service_name(self) -> str | None:
        """Returns the name of the created service, or None if cancelled."""
        return self.__created_service_name

    def _accept(self):
        service_name = self.serviceName_lineEdit.text().strip()

        if not service_name:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Please enter a service name."))
            return

        # Check for duplicate
        try:
            existing = pgserviceparser_full_config()
            if service_name in existing:
                QMessageBox.critical(
                    self,
                    self.tr("Error"),
                    self.tr(f"Service name '{service_name}' already exists."),
                )
                return
        except Exception:
            pass  # If config file doesn't exist yet, that's fine

        settings = {}
        if self.host_lineEdit.text().strip():
            settings["host"] = self.host_lineEdit.text().strip()
        if self.port_lineEdit.text().strip():
            settings["port"] = self.port_lineEdit.text().strip()
        if self.dbname_lineEdit.text().strip():
            settings["dbname"] = self.dbname_lineEdit.text().strip()
        if self.user_lineEdit.text().strip():
            settings["user"] = self.user_lineEdit.text().strip()
        if self.password_lineEdit.text():
            settings["password"] = self.password_lineEdit.text()
        if self.sslmode_comboBox.currentData():
            settings["sslmode"] = self.sslmode_comboBox.currentData()

        try:
            pgserviceparser_write_service(
                service_name=service_name,
                settings=settings,
                create_if_not_found=True,
            )
        except Exception as e:
            error_text = self.tr(f"Error writing the new service configuration:\n{e}.")
            logger.error(error_text)
            QMessageBox.critical(self, self.tr("Error"), error_text)
            return

        self.__created_service_name = service_name
        logger.info(f"Created new PG service '{service_name}'.")
        super().accept()
