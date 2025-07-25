import os
import re
import shutil

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QWidget

from ..core.module_package import ModulePackage
from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import QtUtils

DIALOG_UI = PluginUtils.get_ui_class("project_widget.ui")


class ProjectWidget(QWidget, DIALOG_UI):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)

        self.project_install_pushButton.clicked.connect(self.__projectInstallClicked)
        self.project_seeChangelog_pushButton.clicked.connect(self.__projectSeeChangelogClicked)

        self.__current_module_package = None
        self.__current_service = None

    def setModulePackage(self, module_package: ModulePackage):
        self.__current_module_package = module_package
        self.__packagePrepareGetProjectFilename()

    def setService(self, service):
        self.__current_service = service

    def __packagePrepareGetProjectFilename(self):
        asset_project = self.__current_module_package.asset_project
        if asset_project is None:
            self.project_info_label.setText(
                self.tr("No project asset available for this module version.")
            )
            QtUtils.setForegroundColor(self.project_info_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.project_info_label, True)
            return

        # Check if the directory exists
        if not os.path.exists(asset_project.package_dir):
            self.project_info_label.setText(
                self.tr(f"Project directory '{asset_project.package_dir}' does not exist.")
            )
            QtUtils.setForegroundColor(self.project_info_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.project_info_label, True)
            return

        project_file = None
        for root, dirs, files in os.walk(asset_project.package_dir):
            for file in files:
                if file.endswith(".qgz") or file.endswith(".qgs"):
                    project_file = os.path.join(root, file)
                    break

            if project_file:
                break

        if project_file is None:
            self.project_info_label.setText(
                self.tr(
                    f"No QGIS project file (.qgz or .qgs) found into {asset_project.package_dir}."
                ),
            )
            QtUtils.setForegroundColor(self.project_info_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.project_info_label, True)
            return

        QtUtils.resetForegroundColor(self.project_info_label)
        QtUtils.setFontItalic(self.project_info_label, False)
        self.project_info_label.setText(
            f"<a href='file://{asset_project.package_dir}'>{asset_project.package_dir}</a>",
        )

    def __projectInstallClicked(self):

        if self.__current_module_package is None:
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("Please select a module and version first."),
            )
            return

        asset_project = self.__current_module_package.asset_project
        if asset_project is None:
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("No project asset available for this module version."),
            )
            return

        install_destination = QFileDialog.getExistingDirectory(
            self,
            self.tr("Select installation directory"),
            "",
            QFileDialog.Option.ShowDirsOnly,
        )

        if not install_destination:
            return

        # Copy the project files to the selected directory
        try:
            # Copy all files from assset_project to install_destination
            for item in os.listdir(asset_project.package_dir):
                source_path = os.path.join(asset_project.package_dir, item)
                destination_path = os.path.join(install_destination, item)

                if os.path.isdir(source_path):
                    shutil.copytree(source_path, destination_path, dirs_exist_ok=True)

                elif item.endswith(".qgs"):
                    with open(source_path) as original_project:
                        contents = original_project.read()

                    if self.__current_service is not None:
                        contents = re.sub(
                            r"service='[^']+'", f"service='{self.__current_service}'", contents
                        )
                    else:
                        logger.warning(
                            "No service set, skipping service replacement in project file."
                        )

                    installed_path = os.path.join(install_destination, item)
                    with open(installed_path, "w") as output_file:
                        output_file.write(contents)

                else:
                    shutil.copy2(source_path, destination_path)

            QMessageBox.information(
                self,
                self.tr("Project installed"),
                self.tr(f"Project files have been copied to '{install_destination}'."),
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Failed to copy project file: {e}"),
            )
            return

    def __projectSeeChangelogClicked(self):
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
