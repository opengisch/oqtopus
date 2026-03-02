from qgis.PyQt.QtWidgets import QApplication, QDialog, QMessageBox, QStyle

from ..core.settings import Settings
from ..utils.plugin_utils import PluginUtils

DIALOG_UI = PluginUtils.get_ui_class("settings_dialog.ui")


class SettingsDialog(QDialog, DIALOG_UI):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        self.githubToken_lineEdit.setText(Settings().github_token.value())
        self.allow_multiple_modules_checkBox.setChecked(Settings().allow_multiple_modules.value())
        self.show_experimental_modules_checkBox.setChecked(
            Settings().show_experimental_modules.value()
        )

        # Load log column visibility settings
        self.log_show_datetime_checkBox.setChecked(Settings().log_show_datetime.value())
        self.log_show_level_checkBox.setChecked(Settings().log_show_level.value())
        self.log_show_module_checkBox.setChecked(Settings().log_show_module.value())

        self.helpButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton)
        )
        self.helpButton.clicked.connect(self.__show_github_token_help)

    def accept(self):
        Settings().github_token.setValue(self.githubToken_lineEdit.text())
        Settings().allow_multiple_modules.setValue(
            self.allow_multiple_modules_checkBox.isChecked()
        )
        Settings().show_experimental_modules.setValue(
            self.show_experimental_modules_checkBox.isChecked()
        )
        Settings().log_show_datetime.setValue(self.log_show_datetime_checkBox.isChecked())
        Settings().log_show_level.setValue(self.log_show_level_checkBox.isChecked())
        Settings().log_show_module.setValue(self.log_show_module_checkBox.isChecked())
        super().accept()

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
