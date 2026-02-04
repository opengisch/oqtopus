from qgis.PyQt.QtWidgets import QApplication, QDialog, QMessageBox, QStyle

from ..utils.plugin_utils import PluginUtils

DIALOG_UI = PluginUtils.get_ui_class("settings_dialog.ui")


class SettingsDialog(QDialog, DIALOG_UI):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        self.githubToken_lineEdit.setText(PluginUtils.get_github_token())
        self.allow_multiple_modules_checkBox.setChecked(PluginUtils.get_allow_multiple_modules())

        self.helpButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton)
        )
        self.helpButton.clicked.connect(self.__show_github_token_help)

    def accept(self):
        PluginUtils.set_github_token(self.githubToken_lineEdit.text())
        PluginUtils.set_allow_multiple_modules(self.allow_multiple_modules_checkBox.isChecked())
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
