import os
import shutil
import tempfile
import zipfile

from qgis.PyQt.QtCore import QDir, QStandardPaths, QUrl
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

        # Determine QGIS user plugins directory (profile/python/plugins)
        try:
            from qgis.core import QgsApplication

            qgis_settings_dir = QgsApplication.qgisSettingsDirPath()
        except Exception:
            qgis_settings_dir = None

        if not qgis_settings_dir:
            answer = QMessageBox.question(
                self,
                self.tr("Error"),
                self.tr(
                    "Can't determine QGIS profile directory automatically. Please open the profile folder or cancel."
                ),
                QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return

            # No qgis classes available: look into usual Qt settings folder
            qgis_app_dir = QStandardPaths.locate(
                QStandardPaths.StandardLocation.GenericDataLocation,
                "QGIS/QGIS3/profiles",
                QStandardPaths.LocateOption.LocateDirectory,
            )

            qgis_settings_dir = QFileDialog.getExistingDirectory(
                self,
                self.tr("Open QGIS Profile Folder"),
                qgis_app_dir,
            )
            if not qgis_settings_dir:
                return

        plugins_dir = os.path.join(qgis_settings_dir, "python", "plugins")

        # Ensure plugins directory exists (create if necessary)
        try:
            os.makedirs(plugins_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Can't create plugins directory '{plugins_dir}': {e}"),
            )
            return

        # Extract zip to a temporary directory and move to plugins folder
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with zipfile.ZipFile(asset_plugin.package_zip, "r") as zf:
                    zf.extractall(tmpdir)

                # Inspect top-level entries
                qdir = QDir(tmpdir)
                entries_info = qdir.entryInfoList(QDir.Filter.NoDotAndDotDot | QDir.Filter.Dirs)
                # Require exactly one top-level directory (well-formed plugin zip)
                if len(entries_info) != 1:
                    QMessageBox.critical(
                        self,
                        self.tr("Invalid plugin package"),
                        self.tr(
                            "The plugin zip must contain exactly one top-level directory. "
                            "Please provide a properly packaged plugin."
                        ),
                    )
                    return

                dest_name = entries_info[0].fileName()
                src_path = os.path.join(tmpdir, dest_name)
                dest_path = os.path.join(plugins_dir, dest_name)

                # If destination exists, ask user whether to overwrite
                if os.path.exists(dest_path):
                    res = QMessageBox.question(
                        self,
                        self.tr("Overwrite plugin"),
                        self.tr(
                            f"The plugin '{dest_name}' already exists in the QGIS plugins folder. Overwrite?"
                        ),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if res != QMessageBox.StandardButton.Yes:
                        return
                    # Remove existing plugin directory
                    try:
                        if os.path.islink(dest_path) or os.path.isfile(dest_path):
                            os.remove(dest_path)
                        else:
                            shutil.rmtree(dest_path)
                    except Exception as e:
                        QMessageBox.critical(
                            self,
                            self.tr("Error"),
                            self.tr(f"Failed to remove existing plugin '{dest_path}': {e}"),
                        )
                        return

                # Move the extracted plugin into plugins directory
                try:
                    shutil.move(src_path, dest_path)
                except Exception:
                    # If move fails (cross-device), fallback to copytree
                    try:
                        shutil.copytree(src_path, dest_path)
                    except Exception as e2:
                        QMessageBox.critical(
                            self,
                            self.tr("Error"),
                            self.tr(f"Failed to install plugin to '{dest_path}': {e2}"),
                        )
                        return

            QMessageBox.information(
                self,
                self.tr("Plugin installed"),
                self.tr(
                    f"Plugin '{dest_name}' installed to QGIS profile plugins folder:\n{dest_path}\n\nYou may need to restart QGIS or enable the plugin from the Plugin Manager."
                ),
            )

        except zipfile.BadZipFile:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("The plugin package is not a valid zip archive."),
            )
            return
        except Exception as e:
            logger.exception("Unexpected error during plugin installation")
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Failed to install plugin: {e}"),
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
