import yaml
from qgis.PyQt.QtCore import Qt, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget

from ..core.module import Module
from ..core.module_package import ModulePackage
from ..core.modules_config import ModulesConfig
from ..core.package_prepare_task import PackagePrepareTask, PackagePrepareTaskCanceled
from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import CriticalMessageBox, OverrideCursor, QtUtils

DIALOG_UI = PluginUtils.get_ui_class("module_selection_widget.ui")


class ModuleSelectionWidget(QWidget, DIALOG_UI):

    module_package_SPECIAL_LOAD_DEVELOPMENT = "Load development versions"

    signal_loadingStarted = pyqtSignal()
    signal_loadingFinished = pyqtSignal()

    def __init__(self, modules_config_path, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)

        self.__current_module = None
        self.__current_module_package = None
        self.__modules_config = None

        try:
            with modules_config_path.open() as f:
                data = yaml.safe_load(f)
                self.__modules_config = ModulesConfig(**data)
        except Exception as e:
            logger.error(f"Error loading modules config from {modules_config_path}: {e}")
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Can't load modules configuration from '{modules_config_path}': {e}"),
            )
            self.__modules_config = None

        self.module_progressBar.setVisible(False)

        self.module_module_comboBox.clear()
        self.module_module_comboBox.addItem(self.tr("Please select a module"), None)
        if self.__modules_config is not None:
            for config_module in self.__modules_config.modules:
                module = Module(
                    name=config_module.name,
                    organisation=config_module.organisation,
                    repository=config_module.repository,
                    parent=self,
                )
                self.module_module_comboBox.addItem(module.name, module)
                module.signal_versionsLoaded.connect(self.__loadVersionsFinished)
                module.signal_developmentVersionsLoaded.connect(
                    self.__loadDevelopmentVersionsFinished
                )

        self.module_latestVersion_label.setText("")
        QtUtils.setForegroundColor(self.module_latestVersion_label, PluginUtils.COLOR_GREEN)

        self.module_package_comboBox.clear()
        self.module_package_comboBox.addItem(self.tr("Please select a version"), None)

        self.module_zipPackage_groupBox.setVisible(False)

        self.module_module_comboBox.currentIndexChanged.connect(self.__moduleChanged)
        self.module_package_comboBox.currentIndexChanged.connect(self.__moduleVersionChanged)
        self.module_seeChangeLog_pushButton.clicked.connect(self.__seeChangeLogClicked)
        self.module_browseZip_toolButton.clicked.connect(self.__moduleBrowseZipClicked)

        self.__packagePrepareTask = PackagePrepareTask(self)
        self.__packagePrepareTask.finished.connect(self.__packagePrepareTaskFinished)
        self.__packagePrepareTask.signalPackagingProgress.connect(
            self.__packagePrepareTaskProgress
        )

    def close(self):
        if self.__packagePrepareTask.isRunning():
            self.__packagePrepareTask.cancel()
            self.__packagePrepareTask.wait()

    def getSelectedModulePackage(self):
        return self.__current_module_package

    def lastError(self):
        """
        Returns the last error occurred during the loading process.
        If no error occurred, returns None.
        """
        return self.__packagePrepareTask.lastError

    def __moduleChanged(self, index):
        if self.module_module_comboBox.currentData() == self.__current_module:
            return

        self.__current_module = self.module_module_comboBox.currentData()

        self.module_latestVersion_label.setText("")
        self.module_package_comboBox.clear()
        self.module_package_comboBox.addItem(self.tr("Please select a version"), None)

        if self.__current_module is None:
            return

        if self.__current_module.versions == list():
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.__current_module.start_load_versions()

    def __moduleVersionChanged(self, index):

        if (
            self.module_package_comboBox.currentData()
            == self.module_package_SPECIAL_LOAD_DEVELOPMENT
        ):
            self.__loadDevelopmentVersions()
            return

        if self.__packagePrepareTask.isRunning():
            logger.info("Package prepare task is running, canceling it.")
            self.__packagePrepareTask.cancel()
            self.__packagePrepareTask.wait()

        self.__current_module_package = self.module_package_comboBox.currentData()
        if self.__current_module_package is None:
            return

        if self.__current_module_package.type == self.__current_module_package.Type.FROM_ZIP:
            self.module_zippackage_groupBox.setVisible(True)
            return
        else:
            self.module_zipPackage_groupBox.setVisible(False)

        loading_text = self.tr(
            f"Loading packages for module '{self.module_module_comboBox.currentText()}' version '{self.__current_module_package.display_name()}'..."
        )
        self.module_information_label.setText(loading_text)
        QtUtils.resetForegroundColor(self.module_information_label)
        logger.info(loading_text)

        self.module_informationProject_label.setText("-")
        self.module_informationPlugin_label.setText("-")

        self.__packagePrepareTask.startFromModulePackage(self.__current_module_package)

        self.signal_loadingStarted.emit()
        self.module_progressBar.setVisible(True)

    def __loadDevelopmentVersions(self):
        if self.__current_module is None:
            return

        if self.__current_module.development_versions == list():
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.__current_module.start_load_development_versions()

    def __moduleBrowseZipClicked(self):
        filename, format = QFileDialog.getOpenFileName(
            self, self.tr("Open from zip"), None, self.tr("Zip package (*.zip)")
        )

        if filename == "":
            return

        self.module_fromZip_lineEdit.setText(filename)

        try:
            with OverrideCursor(Qt.CursorShape.WaitCursor):
                self.__loadModuleFromZip(filename)
        except Exception as exception:
            CriticalMessageBox(
                self.tr("Error"), self.tr("Can't load module from zip file:"), exception, self
            ).exec()
            return

    def __loadModuleFromZip(self, filename):

        if self.__packagePrepareTask.isRunning():
            self.__packagePrepareTask.cancel()
            self.__packagePrepareTask.wait()

        self.__packagePrepareTask.startFromZip(filename)

        self.signal_loadingStarted.emit()
        self.module_progressBar.setVisible(True)

    def __packagePrepareTaskFinished(self):
        logger.info("Load package task finished")

        self.signal_loadingFinished.emit()
        self.module_progressBar.setVisible(False)

        if isinstance(self.__packagePrepareTask.lastError, PackagePrepareTaskCanceled):
            logger.info("Load package task was canceled by user.")
            self.module_information_label.setText(self.tr("Package loading canceled."))
            QtUtils.setForegroundColor(self.module_information_label, PluginUtils.COLOR_WARNING)
            return

        if self.__packagePrepareTask.lastError is not None:
            error_text = self.tr("Can't load module package:")
            CriticalMessageBox(
                self.tr("Error"), error_text, self.__packagePrepareTask.lastError, self
            ).exec()
            self.module_information_label.setText(error_text)
            QtUtils.setForegroundColor(self.module_information_label, PluginUtils.COLOR_WARNING)
            return

        package_dir = self.module_package_comboBox.currentData().source_package_dir
        logger.info(f"Package loaded into '{package_dir}'")
        QtUtils.resetForegroundColor(self.module_information_label)
        self.module_information_label.setText(
            f"<a href='file://{package_dir}'>{package_dir}</a>",
        )

        asset_project = self.module_package_comboBox.currentData().asset_project
        if asset_project:
            self.module_informationProject_label.setText(
                f"<a href='file://{asset_project.package_dir}'>{asset_project.package_dir}</a>",
            )
        else:
            self.module_informationProject_label.setText("No asset available")

        asset_plugin = self.module_package_comboBox.currentData().asset_plugin
        if asset_plugin:
            self.module_informationPlugin_label.setText(
                f"<a href='file://{asset_plugin.package_dir}'>{asset_plugin.package_dir}</a>",
            )
        else:
            self.module_informationPlugin_label.setText("No asset available")

    def __packagePrepareTaskProgress(self, progress):
        loading_text = self.tr("Load package task running...")
        logger.info(loading_text)
        self.module_information_label.setText(loading_text)

    def __seeChangeLogClicked(self):
        if self.__current_module_package is None:
            QMessageBox.warning(
                self,
                self.tr("Can't open changelog"),
                self.tr("Please select a module and version first."),
            )
            return

        if self.__current_module_package.type == ModulePackage.Type.FROM_ZIP:
            QMessageBox.warning(
                self,
                self.tr("Can't open changelog"),
                self.tr("Changelog is not available for Zip packages."),
            )
            return

        if self.__current_module_package.html_url is None:
            QMessageBox.warning(
                self,
                self.tr("Can't open changelog"),
                self.tr(
                    f"Changelog not available for version '{self.__current_module_package.display_name()}'."
                ),
            )
            return

        changelog_url = self.__current_module_package.html_url
        logger.info(f"Opening changelog URL: {changelog_url}")
        QDesktopServices.openUrl(QUrl(changelog_url))

    def __loadVersionsFinished(self, error):
        logger.info("Loading versions finished")

        QApplication.restoreOverrideCursor()
        self.signal_loadingFinished.emit()
        self.module_progressBar.setVisible(False)

        if error:
            if "rate limit exceeded for url" in error.lower():
                QMessageBox.critical(
                    self,
                    self.tr("GitHub API Rate Limit Exceeded"),
                    self.tr(
                        "Oqtopus needs to download release data from GitHub to work properly.<br><br>"
                        "GitHub limits the number of requests that can be made without authentication. "
                        "You have reached the maximum number of requests allowed for unauthenticated users.<br><br>"
                        "To continue using this feature, please create a free GitHub personal access token and enter it in the Settings dialog.<br><br>"
                        "This will increase your request limit.<br><br>"
                        "<b>How to get a token:</b><br>"
                        "1. Go to <a href='https://github.com/settings/tokens'>GitHub Personal Access Tokens</a>.<br>"
                        "2. Click <b>Generate new token</b> and select the <code>repo</code> scope.<br>"
                        "3. Copy the generated token and paste it in the Settings dialog of this application."
                    ),
                )
                return

            error_text = self.tr(f"Can't load module versions: {error}")
            QMessageBox.critical(self, self.tr("Error"), error_text)
            self.module_information_label.setText(error_text)
            QtUtils.setForegroundColor(self.module_information_label, PluginUtils.COLOR_WARNING)
            return

        for module_package in self.__current_module.versions:
            self.module_package_comboBox.addItem(module_package.display_name(), module_package)

        if self.__current_module.latest_version is not None:
            self.module_latestVersion_label.setText(
                f"Latest: {self.__current_module.latest_version.name}"
            )

        self.module_package_comboBox.insertSeparator(self.module_package_comboBox.count())
        self.module_package_comboBox.addItem(
            self.tr("Load from ZIP file"),
            ModulePackage(
                module=self.__current_module,
                organisation=self.__current_module.organisation,
                repository=self.__current_module.repository,
                json_payload=None,
                type=ModulePackage.Type.FROM_ZIP,
            ),
        )

        self.module_package_comboBox.insertSeparator(self.module_package_comboBox.count())
        self.module_package_comboBox.addItem(
            self.tr("Load development branches"), self.module_package_SPECIAL_LOAD_DEVELOPMENT
        )

        self.module_progressBar.setVisible(False)
        logger.info(f"Versions loaded for module '{self.__current_module.name}'.")

    def __loadDevelopmentVersionsFinished(self, error):
        logger.info("Loading development versions finished")

        QApplication.restoreOverrideCursor()
        self.signal_loadingFinished.emit()
        self.module_progressBar.setVisible(False)

        if error:
            if "rate limit exceeded for url" in error.lower():
                QMessageBox.critical(
                    self,
                    self.tr("GitHub API Rate Limit Exceeded"),
                    self.tr(
                        "Oqtopus needs to download release data from GitHub to work properly.<br><br>"
                        "GitHub limits the number of requests that can be made without authentication. "
                        "You have reached the maximum number of requests allowed for unauthenticated users.<br><br>"
                        "To continue using this feature, please create a free GitHub personal access token and enter it in the Settings dialog.<br><br>"
                        "This will increase your request limit.<br><br>"
                        "<b>How to get a token:</b><br>"
                        "1. Go to <a href='https://github.com/settings/tokens'>GitHub Personal Access Tokens</a>.<br>"
                        "2. Click <b>Generate new token</b> and select the <code>repo</code> scope.<br>"
                        "3. Copy the generated token and paste it in the Settings dialog of this application."
                    ),
                )
                return

            error_text = self.tr(f"Can't load module versions: {error}")
            QMessageBox.critical(self, self.tr("Error"), error_text)
            self.module_information_label.setText(error_text)
            QtUtils.setForegroundColor(self.module_information_label, PluginUtils.COLOR_WARNING)
            return

        if self.__current_module.development_versions == list():
            QMessageBox.warning(
                self,
                self.tr("No development versions found"),
                self.tr("No development versions found for this module."),
            )
            return

        self.module_package_comboBox.removeItem(self.module_package_comboBox.count() - 1)
        self.module_package_comboBox.setCurrentIndex(0)

        for module_package in self.__current_module.development_versions:
            self.module_package_comboBox.addItem(module_package.display_name(), module_package)
