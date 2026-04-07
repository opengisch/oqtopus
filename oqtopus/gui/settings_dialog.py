from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox, QStyle

from ..core.settings import Settings
from ..utils.plugin_utils import PluginUtils

DIALOG_UI = PluginUtils.get_ui_class("settings_dialog.ui")


class SettingsDialog(QDialog, DIALOG_UI):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        self.githubToken_lineEdit.setEchoMode(QLineEdit.EchoMode.Password)

        # Show a placeholder if a token exists, without accessing the
        # encrypted auth DB (avoids a master-password prompt on dialog open).
        self._token_loaded = False
        self._token_dirty = False
        if Settings.has_github_token():
            self.githubToken_lineEdit.setPlaceholderText(self.tr("Token stored in auth database"))
        self.githubToken_lineEdit.textEdited.connect(self.__on_token_edited)

        # Toggle visibility action inside the line edit
        self._toggle_token_action = self.githubToken_lineEdit.addAction(
            QIcon(PluginUtils.get_plugin_icon_path("eye.svg")),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self._toggle_token_action.setToolTip(self.tr("Show/hide token"))
        self._toggle_token_action.triggered.connect(self.__toggle_token_visibility)
        self.allow_multiple_modules_checkBox.setChecked(Settings().allow_multiple_modules.value())
        self.show_experimental_modules_checkBox.setChecked(
            Settings().show_experimental_modules.value()
        )

        # Load log column visibility settings
        self.log_show_datetime_checkBox.setChecked(Settings().log_show_datetime.value())
        self.log_show_level_checkBox.setChecked(Settings().log_show_level.value())
        self.log_show_module_checkBox.setChecked(Settings().log_show_module.value())
        self.auto_load_development_versions_checkBox.setChecked(
            Settings().auto_load_development_versions.value()
        )

        self.helpButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton)
        )
        self.helpButton.clicked.connect(self.__show_github_token_help)

    def accept(self):
        if self._token_dirty:
            Settings.store_github_token(self.githubToken_lineEdit.text())
        Settings().allow_multiple_modules.setValue(
            self.allow_multiple_modules_checkBox.isChecked()
        )
        Settings().show_experimental_modules.setValue(
            self.show_experimental_modules_checkBox.isChecked()
        )
        Settings().log_show_datetime.setValue(self.log_show_datetime_checkBox.isChecked())
        Settings().log_show_level.setValue(self.log_show_level_checkBox.isChecked())
        Settings().log_show_module.setValue(self.log_show_module_checkBox.isChecked())
        Settings().auto_load_development_versions.setValue(
            self.auto_load_development_versions_checkBox.isChecked()
        )
        super().accept()

    def __on_token_edited(self):
        self._token_dirty = True

    def __toggle_token_visibility(self):
        if self.githubToken_lineEdit.echoMode() == QLineEdit.EchoMode.Password:
            # Fetch the real token from the auth DB on first reveal
            if not self._token_loaded and not self._token_dirty:
                token = Settings.get_github_token()
                if token:
                    self.githubToken_lineEdit.setText(token)
                self._token_loaded = True
            self.githubToken_lineEdit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.githubToken_lineEdit.setEchoMode(QLineEdit.EchoMode.Password)

    def __show_github_token_help(self):
        QMessageBox.information(
            self,
            "GitHub Access Token Help",
            "<b>GitHub Access Token</b><br>"
            "oQtopus needs to download release data from GitHub to work properly. "
            "GitHub limits the number of requests that can be made without authentication. "
            "A personal access token is required to access private repositories or to increase API rate limits.<br><br>"
            "To generate a token:<br>"
            "1. Go to <a href='https://github.com/settings/tokens'>GitHub Personal Access Tokens</a>.<br>"
            "2. Click <b>Generate new token</b>.<br>"
            "3. Select the <code>repo</code> scope for most operations.<br>"
            "4. Copy and paste the generated token here.",
        )
