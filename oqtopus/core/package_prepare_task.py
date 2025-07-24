import os
import shutil
import zipfile

import requests
from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..utils.plugin_utils import PluginUtils, logger


class PackagePrepareTaskCanceled(Exception):
    pass


class PackagePrepareTask(QThread):
    """
    This class is responsible for preparing the package for the Oqtopus module management tool.
    It inherits from QThread to run the preparation process in a separate thread.
    """

    signalPackagingProgress = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.module_package = None

        self.__destination_directory = None

        self.__canceled = False
        self.lastError = None

    def startFromZip(self, zip_file: str):

        self.module_package = None

        self.__canceled = False
        self.start()

    def startFromModulePackage(self, module_package):
        self.module_package = module_package

        self.__canceled = False
        self.start()

    def cancel(self):
        self.__canceled = True

    def run(self):
        """
        The main method that runs when the thread starts.
        """

        try:
            if self.module_package is None:
                raise Exception(self.tr("No module version provided."))

            self.__destination_directory = self.__prepareDestinationDirectory()

            self.__download_module_assets(self.module_package)
            self.lastError = None

        except Exception as e:
            # Handle any exceptions that occur during processing
            logger.critical(f"Package prepare task error: {e}")
            self.lastError = e

    def __prepareDestinationDirectory(self):
        """
        Prepare the destination directory for the module package.
        This method creates a temporary directory for the package.
        """
        temp_dir = PluginUtils.plugin_temp_path()
        destination_directory = os.path.join(
            temp_dir,
            self.module_package.organisation,
            self.module_package.repository,
            self.module_package.name,
        )
        os.makedirs(destination_directory, exist_ok=True)

        return destination_directory

    def __download_module_assets(self, module_package):

        # Download the source
        zip_file = self.__download_module_asset(module_package.download_url, "source.zip")
        module_package.source_package_zip = zip_file
        package_dir = self.__extract_zip_file(zip_file)
        module_package.source_package_dir = package_dir

        # Download the release assets
        self.__checkForCanceled()
        if module_package.asset_project is not None:
            zip_file = self.__download_module_asset(
                module_package.asset_project.download_url,
                module_package.asset_project.type.value + ".zip",
            )
            package_dir = self.__extract_zip_file(zip_file)
            module_package.asset_project.package_zip = zip_file
            module_package.asset_project.package_dir = package_dir

        self.__checkForCanceled()
        if module_package.asset_plugin is not None:
            zip_file = self.__download_module_asset(
                module_package.asset_plugin.download_url,
                module_package.asset_plugin.type.value + ".zip",
            )
            package_dir = self.__extract_zip_file(zip_file)
            module_package.asset_plugin.package_zip = zip_file
            module_package.asset_plugin.package_dir = package_dir

    def __download_module_asset(self, url: str, filename: str):

        zip_file = os.path.join(self.__destination_directory, filename)

        # Streaming, so we can iterate over the response.
        response = requests.get(url, allow_redirects=True, stream=True)

        # Raise an exception in case of http errors
        response.raise_for_status()

        self.__checkForCanceled()

        logger.info(f"Downloading from '{url}' to '{zip_file}'")
        data_size = 0
        with open(zip_file, "wb") as file:
            next_emit_threshold = 10 * 1024 * 1024  # 10MB threshold
            for data in response.iter_content(chunk_size=None):
                file.write(data)

                self.__checkForCanceled()

                data_size += len(data)
                if data_size >= next_emit_threshold:  # Emit signal when threshold is exceeded
                    self.signalPackagingProgress.emit(data_size)
                    next_emit_threshold += 10 * 1024 * 1024  # Update to the next threshold

        return zip_file

    def __extract_zip_file(self, zip_file):
        # Unzip the file to plugin temp dir
        try:
            with zipfile.ZipFile(zip_file, "r") as zip_ref:
                # Find the top-level directory
                zip_dirname = zip_ref.namelist()[0].split("/")[0]
                package_dir = os.path.join(self.__destination_directory, zip_dirname)

                if os.path.exists(package_dir):
                    shutil.rmtree(package_dir)

                zip_ref.extractall(self.__destination_directory)

        except zipfile.BadZipFile:
            raise Exception(self.tr(f"The selected file '{zip_file}' is not a valid zip archive."))

        return package_dir

    def __checkForCanceled(self):
        """
        Check if the task has been canceled.
        """
        if self.__canceled:
            raise PackagePrepareTaskCanceled(self.tr("The task has been canceled."))
