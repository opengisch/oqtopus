import os
import re
import shutil

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QFileDialog, QWidget

try:
    from qgis.core import QgsProject

    HAS_QGIS = True
except ImportError:
    HAS_QGIS = False

from ..core.module_package import ModulePackage
from ..utils.plugin_utils import PluginUtils, logger
from ..utils.qt_utils import QtUtils
from .message_bar import MessageBar

DIALOG_UI = PluginUtils.get_ui_class("project_widget.ui")


class ProjectWidget(QWidget, DIALOG_UI):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)

        self.project_install_pushButton.clicked.connect(self.__projectInstallClicked)
        self.project_seeChangelog_pushButton.clicked.connect(self.__projectSeeChangelogClicked)
        self.project_openInQgis_pushButton.clicked.connect(self.__openProjectInQgis)

        # "Open in QGIS" is only available when running inside QGIS
        self.project_openInQgis_pushButton.setVisible(HAS_QGIS)

        self.__current_module_package = None
        self.__current_service = None

    def setModulePackage(self, module_package: ModulePackage):
        self.__current_module_package = module_package
        self.__updateProjectFilename()
        self.__updateOpenInQgisButton()

    def clearModulePackage(self):
        """Clear module package state and reset UI."""
        self.__current_module_package = None
        self.__updateProjectFilename()
        self.__updateOpenInQgisButton()

    def setService(self, service):
        self.__current_service = service
        self.__updateProjectFilename()

    def __updateProjectFilename(self):

        if self.__current_module_package is None:
            self.project_info_label.setText(self.tr("No module package selected."))
            QtUtils.setForegroundColor(self.project_info_label, PluginUtils.COLOR_WARNING)
            QtUtils.setFontItalic(self.project_info_label, True)
            return

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
        if self.__current_service:
            self.project_info_label.setText(
                f"Project will use PG Service '{self.__current_service}' for database connection"
            )
        else:
            self.project_info_label.setText(
                "Project will use the default service. Please set a service in the database connection tab if you need a specific one."
            )

    def __projectInstallClicked(self):

        if self.__current_module_package is None:
            MessageBar.pushWarningToBar(self, self.tr("Please select a module and version first."))
            return

        asset_project = self.__current_module_package.asset_project
        if asset_project is None:
            MessageBar.pushWarningToBar(
                self, self.tr("No project asset available for this module version.")
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

            MessageBar.pushSuccessToBar(
                self, self.tr(f"Project files have been copied to '{install_destination}'.")
            )

            # Remember installed project file path for "Open in QGIS"
            self.__saveInstalledProjectPath(install_destination)
        except Exception as e:
            MessageBar.pushErrorToBar(self, self.tr(f"Failed to copy project file: {e}"))
            return

    def __dynamicKeyParts(self):
        """Return the dynamic key parts [module_id, version] for the settings entry."""
        if self.__current_module_package is None:
            return None
        module_id = self.__current_module_package.module.id
        version = self.__current_module_package.name or ""
        return [module_id, version]

    def __saveInstalledProjectPath(self, install_destination):
        """Find the .qgz/.qgs file in *install_destination* and persist its path."""
        if not HAS_QGIS:
            return
        key_parts = self.__dynamicKeyParts()
        if key_parts is None:
            return
        # Find the project file that was copied
        from ..core.settings import Settings

        for item in os.listdir(install_destination):
            if item.endswith((".qgz", ".qgs")):
                project_path = os.path.join(install_destination, item)
                Settings().installed_project_path.setValue(
                    project_path, dynamicKeyPartList=key_parts
                )
                logger.info(f"Saved installed project path: {project_path}")
                self.__updateOpenInQgisButton()
                return

    def __getInstalledProjectPath(self):
        """Return the stored project file path for the current module/version, or None."""
        if not HAS_QGIS:
            return None
        key_parts = self.__dynamicKeyParts()
        if key_parts is None:
            return None
        from ..core.settings import Settings

        path = Settings().installed_project_path.value(dynamicKeyPartList=key_parts)
        if path and os.path.isfile(path):
            return path
        return None

    def __updateOpenInQgisButton(self):
        """Enable the 'Open in QGIS' button only when a saved project exists."""
        if not HAS_QGIS:
            return
        project_path = self.__getInstalledProjectPath()
        self.project_openInQgis_pushButton.setEnabled(project_path is not None)
        if project_path:
            self.project_openInQgis_pushButton.setToolTip(project_path)
        else:
            self.project_openInQgis_pushButton.setToolTip(
                self.tr("Install the project first to enable this button.")
            )

    def __openProjectInQgis(self):
        """Open the remembered project file in QGIS."""
        project_path = self.__getInstalledProjectPath()
        if project_path is None:
            MessageBar.pushWarningToBar(
                self,
                self.tr("No installed project found. Please install the project first."),
            )
            return
        logger.info(f"Opening project in QGIS: {project_path}")
        QgsProject.instance().read(project_path)  # type: ignore[possibly-undefined]

    def __projectSeeChangelogClicked(self):
        if self.__current_module_package is None:
            MessageBar.pushWarningToBar(self, self.tr("Please select a module and version first."))
            return

        if self.__current_module_package.type == ModulePackage.Type.FROM_ZIP:
            MessageBar.pushWarningToBar(
                self, self.tr("Changelog is not available for Zip packages.")
            )
            return

        if self.__current_module_package.html_url is None:
            MessageBar.pushWarningToBar(
                self,
                self.tr(
                    f"Changelog not available for version '{self.__current_module_package.display_name()}'."
                ),
            )
            return

        changelog_url = self.__current_module_package.html_url
        logger.info(f"Opening changelog URL: {changelog_url}")
        QDesktopServices.openUrl(QUrl(changelog_url))
