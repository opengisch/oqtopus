import os
import shutil
from zipfile import ZipFile

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
        self.__plugin_name = None

        try:
            from qgis.utils import iface

            self.qgisProfile_label.setText(iface.userProfileManager().userProfile().name())
        except ImportError:
            self.qgisProfile_label.setText("Unknown")

    def setModulePackage(self, module_package: ModulePackage):
        self.__current_module_package = module_package
        self.__plugin_name = None
        self.__packagePrepareGetPluginFilename()

    def clearModulePackage(self):
        """Clear module package state and reset UI."""
        self.__current_module_package = None
        self.info_label.setText(self.tr("No module package selected."))
        QtUtils.setForegroundColor(self.info_label, PluginUtils.COLOR_WARNING)
        QtUtils.setFontItalic(self.info_label, True)

    def __packagePrepareGetPluginFilename(self):
        if self.__current_module_package is None:
            self.info_label.setText(self.tr("No module package selected."))
            QtUtils.setForegroundColor(self.info_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.info_label, True)
            return

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

        # Get the plugin name
        self.__plugin_name = self.__extractPluginName(asset_plugin.package_zip)
        if not self.__plugin_name:
            self.info_label.setText(
                self.tr(f"Couldn't determinate the plugin name for '{asset_plugin.package_zip}'.")
            )
            QtUtils.setForegroundColor(self.info_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.info_label, True)
            return

        # Get the installed plugin current version
        version = self.__getInstalledPluginVersion(self.__plugin_name)
        self.currentVersion_label.setText(version)

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
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Plugin zip file '{asset_plugin.package_zip}' does not exist."),
            )
            return

        try:
            from pyplugin_installer import instance as plugin_installer_instance
            from qgis.core import Qgis
        except ImportError:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Plugin installation is not possible when oQtopus is running standalone."),
            )
            return

        try:
            installer = plugin_installer_instance()
            success = installer.installFromZipFile(asset_plugin.package_zip)

            # installFromZipFile return success from QGIS 3.44.08
            if Qgis.QGIS_VERSION_INT < 34408:
                version = self.__getInstalledPluginVersion(self.__plugin_name)
                QMessageBox.information(
                    self,
                    self.tr("Installation finished"),
                    self.tr(f"Current '{self.__plugin_name}' plugin version is {version}"),
                )
                self.__packagePrepareGetPluginFilename()
                return

            if not success:
                QMessageBox.critical(
                    self,
                    self.tr("Error"),
                    self.tr(f"Plugin '{self.__plugin_name}' installation failed."),
                )
                return

            QMessageBox.information(
                self,
                self.tr("Success"),
                self.tr(f"Plugin '{self.__plugin_name}' installed successfully."),
            )
            self.__packagePrepareGetPluginFilename()

        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Plugin installation failed with an exception: {0}").format(str(e)),
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

    def __extractPluginName(self, package_zip: str) -> str:
        with ZipFile(package_zip, "r") as zip_ref:
            for name in zip_ref.namelist():
                print(f"name: {name}")
                if name.endswith("/metadata.txt"):
                    return name.split("/")[0]
        return ""

    def __getInstalledPluginVersion(self, plugin_name: str):
        try:
            from qgis.utils import pluginMetadata
        except ImportError:
            return self.tr("Unknown")

        version = pluginMetadata(plugin_name, "version")
        if version == "__error__":
            return self.tr("Not installed")

        return version
