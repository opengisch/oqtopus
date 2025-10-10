from qgis.PyQt.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QStyle

from ..utils.plugin_utils import PluginUtils

DIALOG_UI = PluginUtils.get_ui_class("settings_dialog.ui")


class SettingsDialog(QDialog, DIALOG_UI):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setupUi(self)

        self.modulesConfigurationFile_lineEdit.setText(
            PluginUtils.get_modules_configuration_file()
        )
        self.modulesConfigurationFile_toolButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.modulesConfigurationFile_toolButton.clicked.connect(
            self.__select_modules_configuration_file
        )

        self.githubToken_lineEdit.setText(PluginUtils.get_github_token())

        self.githubToken_helpButton.setIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton)
        )
        self.githubToken_helpButton.clicked.connect(self.__show_github_token_help)

    def accept(self):
        PluginUtils.set_modules_configuration_file(self.modulesConfigurationFile_lineEdit.text())
        PluginUtils.set_github_token(self.githubToken_lineEdit.text())
        super().accept()

    def __select_modules_configuration_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Select Modules Configuration File"),
            "",
            self.tr("YAML files (*.yml *.yaml);;All files (*)"),
        )
        if file_path:
            self.modulesConfigurationFile_lineEdit.setText(file_path)

    def __show_github_token_help(self):
        QMessageBox.information(
            self,
            "GitHub Access Token Help",
            "<b>GitHub Access Token</b><br>"
            "Oqtopus needs to download release data from GitHub to work properly. "
            "GitHub limits the number of requests that can be made without authentication. "
            "A personal access token is required to access private repositories or to increase API rate limits.<br><br>"
            "To generate a token:<br>"
            "1. Go to <a href='https://github.com/settings/tokens'>GitHub Personal Access Tokens</a>.<br>"
            "2. Click <b>Generate new token</b>.<br>"
            "3. Select the <code>repo</code> scope for most operations.<br>"
            "4. Copy and paste the generated token here.",
        )
