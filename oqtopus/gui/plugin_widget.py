import os
import shutil

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QWidget

from ..core.module_package import ModulePackage
from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import QtUtils

DIALOG_UI = PluginUtils.get_ui_class("plugin_widget.ui")


class PluginWidget(QWidget, DIALOG_UI):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)

        self.install_pushButton.clicked.connect(self.__installClicked)
        self.seeChangelog_pushButton.clicked.connect(self.__seeChangelogClicked)
        self.copyZipToDirectory_pushButton.clicked.connect(self.__copyZipToDirectoryClicked)

        self.__current_module_package = None

    def setModulePackage(self, module_package: ModulePackage):
        self.__current_module_package = module_package
        self.__packagePrepareGetPluginFilename()

    def __packagePrepareGetPluginFilename(self):
        asset_plugin = self.__current_module_package.asset_plugin
        if asset_plugin is None:
            self.info_label.setText(self.tr("No plugin asset available for this module version."))
            QtUtils.setForegroundColor(self.info_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.info_label, True)
            return

        # Check if the package exists
        if not os.path.exists(asset_plugin.package_zip):
            self.info_label.setText(
                self.tr(f"Plugin zip file '{asset_plugin.package_zip}' does not exist.")
            )
            QtUtils.setForegroundColor(self.info_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.info_label, True)
            return

        QtUtils.resetForegroundColor(self.info_label)
        QtUtils.setFontItalic(self.info_label, False)
        self.info_label.setText(
            f"<a href='file://{asset_plugin.package_zip}'>{asset_plugin.package_zip}</a>",
        )

    def __installClicked(self):
        if self.__current_module_package is None:
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("Please select a module and version first."),
            )
            return

        # Check if the package exists
        asset_plugin = self.__current_module_package.asset_plugin
        if not os.path.exists(asset_plugin.package_zip):
            self.info_label.setText(
                self.tr(f"Plugin zip file '{asset_plugin.package_zip}' does not exist.")
            )
            QtUtils.setForegroundColor(self.info_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.info_label, True)
            return

        QMessageBox.warning(
            self,
            self.tr("Not implemented"),
            self.tr(
                'Installation is not implemented yet.\nAt the moment, you can only copy the plugin zip file to a directory and use "Install from ZIP" in QGIS.'
            ),
        )
        return

    def __seeChangelogClicked(self):
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

    def __copyZipToDirectoryClicked(self):
        if self.__current_module_package is None:
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("Please select a module and version first."),
            )
            return

        # Check if the package exists
        asset_plugin = self.__current_module_package.asset_plugin
        if not os.path.exists(asset_plugin.package_zip):
            self.info_label.setText(
                self.tr(f"Plugin zip file '{asset_plugin.package_zip}' does not exist.")
            )
            QtUtils.setForegroundColor(self.info_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.info_label, True)
            return

        install_destination = QFileDialog.getExistingDirectory(
            self,
            self.tr("Select installation directory"),
            "",
            QFileDialog.Option.ShowDirsOnly,
        )

        if not install_destination:
            return

        # Copy the plugin package to the selected directory
        try:
            shutil.copy2(asset_plugin.package_zip, install_destination)

            QMessageBox.information(
                self,
                self.tr("Plugin copied"),
                self.tr(f"Plugin package has been copied to '{install_destination}'."),
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Failed to copy plugin package: {e}"),
            )
            return
