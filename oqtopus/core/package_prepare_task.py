import os
import shutil
import zipfile

import requests
from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.module_package import ModulePackage
from ..utils.plugin_utils import PluginUtils, logger


class PackagePrepareTaskCanceled(Exception):
    pass


class PackagePrepareTask(QThread):
    """
    This class is responsible for preparing the package for the oQtopus module management tool.
    It inherits from QThread to run the preparation process in a separate thread.
    """

    signalPackagingProgress = pyqtSignal(float, int)  # progress_percent, bytes_downloaded

    def __init__(self, parent=None):
        super().__init__(parent)

        self.module_package = None
        self.from_zip_file = None

        self.__destination_directory = None

        self.__canceled = False
        self.lastError = None

        # Track download progress across all assets
        self.__download_total_expected = 0
        self.__download_total_received = 0
        self.__last_emitted_percent = None

    def startFromZip(self, module_package, zip_file: str):
        self.module_package = module_package
        self.from_zip_file = zip_file

        self.__canceled = False
        self.start()

    def startFromModulePackage(self, module_package):
        self.module_package = module_package
        self.from_zip_file = None

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

            self.__destination_directory = self.__prepare_destination_directory()
            logger.info(f"Destination directory: {self.__destination_directory}")

            # Reset progress tracking
            self.__download_total_expected = 0
            self.__download_total_received = 0
            self.__last_emitted_percent = None

            self.__prepare_module_assets(self.module_package)
            self.lastError = None

        except Exception as e:
            # Handle any exceptions that occur during processing
            logger.critical(f"Package prepare task error: {e}")
            self.lastError = e

    def __prepare_destination_directory(self):
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

    def __prepare_module_assets(self, module_package):

        # For branches and pull requests, content may change - don't use cache
        is_dynamic_content = module_package.type in (
            ModulePackage.Type.BRANCH,
            ModulePackage.Type.PULL_REQUEST,
        )

        # Pre-fetch all file sizes to calculate accurate total progress
        self.__prefetch_download_sizes(module_package, is_dynamic_content)

        # Download the source or use from zip
        zip_file = self.from_zip_file or self.__download_module_asset(
            module_package.download_url, "source.zip", skip_cache=is_dynamic_content
        )

        module_package.source_package_zip = zip_file
        package_dir = self.__extract_zip_file(zip_file)
        module_package.source_package_dir = package_dir

        # Download the release assets
        self.__checkForCanceled()
        if module_package.asset_project is not None:
            zip_file = self.__download_module_asset(
                module_package.asset_project.download_url,
                module_package.asset_project.type.value + ".zip",
                skip_cache=is_dynamic_content,
            )
            package_dir = self.__extract_zip_file(zip_file)
            module_package.asset_project.package_zip = zip_file
            module_package.asset_project.package_dir = package_dir

        self.__checkForCanceled()
        if module_package.asset_plugin is not None:
            zip_file = self.__download_module_asset(
                module_package.asset_plugin.download_url,
                module_package.asset_plugin.type.value + ".zip",
                skip_cache=is_dynamic_content,
            )
            package_dir = self.__extract_zip_file(zip_file)
            module_package.asset_plugin.package_zip = zip_file
            module_package.asset_plugin.package_dir = package_dir

    def __prefetch_download_sizes(self, module_package, skip_cache: bool):
        """Pre-fetch Content-Length for all files to be downloaded for accurate progress."""
        logger.debug("Pre-fetching download sizes...")

        urls_to_check = []

        # Check source if not from zip
        if self.from_zip_file is None:
            urls_to_check.append((module_package.download_url, "source.zip"))

        # Check project asset
        if module_package.asset_project is not None:
            urls_to_check.append(
                (
                    module_package.asset_project.download_url,
                    module_package.asset_project.type.value + ".zip",
                )
            )

        # Check plugin asset
        if module_package.asset_plugin is not None:
            urls_to_check.append(
                (
                    module_package.asset_plugin.download_url,
                    module_package.asset_plugin.type.value + ".zip",
                )
            )

        total_size = 0
        for url, filename in urls_to_check:
            zip_file = os.path.join(self.__destination_directory, filename)

            # If file exists in cache and we're not skipping cache, don't count it
            if not skip_cache and os.path.exists(zip_file):
                try:
                    with zipfile.ZipFile(zip_file, "r") as zip_test:
                        zip_test.testzip()
                    logger.debug(f"File '{filename}' exists in cache, skipping size check")
                    continue
                except (zipfile.BadZipFile, Exception):
                    # Invalid, will need to download
                    pass

            # Get Content-Length via HEAD request
            try:
                response = requests.head(url, allow_redirects=True, timeout=10)
                content_length = response.headers.get("content-length")
                if content_length:
                    file_size = int(content_length)
                    total_size += file_size
                    logger.debug(f"File '{filename}' size: {file_size} bytes")
                else:
                    logger.warning(
                        f"No Content-Length for '{filename}', progress may be inaccurate"
                    )
            except Exception as e:
                logger.warning(f"Failed to get size for '{filename}': {e}")

        self.__download_total_expected = total_size
        logger.info(
            f"Total expected download size: {total_size} bytes ({total_size / (1024 * 1024):.1f} MB)"
        )
        logger.debug(
            f"Progress tracking initialized: expected={self.__download_total_expected}, received={self.__download_total_received}"
        )

        # If we couldn't determine size, use indeterminate progress
        if total_size == 0:
            logger.info("Using indeterminate progress (size unknown)")
            self.signalPackagingProgress.emit(-1.0, 0)

    def __download_module_asset(self, url: str, filename: str, skip_cache: bool = False):

        zip_file = os.path.join(self.__destination_directory, filename)

        # Check if file already exists and is valid
        if not skip_cache and os.path.exists(zip_file):
            try:
                # Try to open it to verify it's a valid zip
                with zipfile.ZipFile(zip_file, "r") as zip_test:
                    zip_test.testzip()  # Test for corrupted files
                logger.info(f"File '{zip_file}' already exists and is valid - skipping download")
                # Still emit some progress to show we're not stuck
                logger.debug(
                    f"Returning from cache: expected={self.__download_total_expected}, received={self.__download_total_received}"
                )
                self.signalPackagingProgress.emit(-1.0, 0)
                return zip_file
            except (zipfile.BadZipFile, Exception) as e:
                logger.warning(f"Existing file '{zip_file}' is invalid ({e}), will re-download")
                os.remove(zip_file)
        elif skip_cache and os.path.exists(zip_file):
            logger.info(
                f"Removing cached file '{zip_file}' because content may have changed (branch/PR)"
            )
            os.remove(zip_file)

        # Streaming, so we can iterate over the response.
        timeout = 60
        logger.info(f"Starting download from '{url}'")
        logger.debug(f"Making HTTP GET request with timeout={timeout}...")

        try:
            response = requests.get(url, allow_redirects=True, stream=True, timeout=timeout)
            logger.debug(f"HTTP GET request completed, status={response.status_code}")
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            raise

        # Raise an exception in case of http errors
        response.raise_for_status()

        self.__checkForCanceled()

        # Get total file size from headers
        content_length = response.headers.get("content-length")
        file_size = int(content_length) if content_length else 0

        if file_size > 0:
            # Size already added in __prefetch_download_sizes, just log it
            logger.info(f"Downloading from '{url}' to '{zip_file}' (size: {file_size} bytes)")
            logger.debug(
                f"Before download: expected={self.__download_total_expected}, received={self.__download_total_received}"
            )
        else:
            logger.info(f"Downloading from '{url}' to '{zip_file}' (size unknown)")
            # Emit indeterminate progress
            self.signalPackagingProgress.emit(-1.0, 0)

        downloaded_size = 0
        chunk_count = 0
        logger.debug("Starting to write file chunks...")
        with open(zip_file, "wb") as file:
            chunk_size = 256 * 1024  # 256KB chunks
            for data in response.iter_content(chunk_size=chunk_size, decode_unicode=False):
                chunk_count += 1
                if chunk_count % 10 == 0:  # Log every 10th chunk
                    logger.debug(
                        f"Downloaded {chunk_count} chunks, {downloaded_size} bytes so far"
                    )
                file.write(data)

                self.__checkForCanceled()

                chunk_len = len(data)
                downloaded_size += chunk_len
                self.__download_total_received += chunk_len

                # Emit progress on percentage change
                self.__emit_progress()

        # Ensure final progress reflects completion
        logger.info(f"Download completed: {chunk_count} chunks, {downloaded_size} bytes total")
        self.__emit_progress(force=True)

        return zip_file

    def __emit_progress(self, force: bool = False):
        """Emit download progress as percentage (0-100) or -1 for indeterminate."""
        if self.__download_total_expected <= 0:
            # Size unknown, emit indeterminate progress with bytes downloaded
            self.signalPackagingProgress.emit(-1.0, self.__download_total_received)
            return

        percent = int((self.__download_total_received * 100) / self.__download_total_expected)
        percent = max(0, min(100, percent))  # Clamp to 0-100

        logger.debug(
            f"Progress: {self.__download_total_received}/{self.__download_total_expected} = {percent}%"
        )

        if force or self.__last_emitted_percent != percent:
            self.__last_emitted_percent = percent
            self.signalPackagingProgress.emit(float(percent), self.__download_total_received)

    def __extract_zip_file(self, zip_file):
        # Unzip the file to plugin temp dir
        logger.info(f"Extracting '{zip_file}'...")
        # Don't set indeterminate here - it confuses the progress when downloading multiple files

        try:
            with zipfile.ZipFile(zip_file, "r") as zip_ref:
                # Find the top-level directory
                zip_dirname = zip_ref.namelist()[0].split("/")[0]
                package_dir = os.path.join(self.__destination_directory, zip_dirname)

                if os.path.exists(package_dir):
                    logger.info(f"Removing existing directory '{package_dir}'")
                    shutil.rmtree(package_dir)

                zip_ref.extractall(self.__destination_directory)
                logger.info(f"Extraction complete: '{package_dir}'")

        except zipfile.BadZipFile:
            raise Exception(self.tr(f"The selected file '{zip_file}' is not a valid zip archive."))

        return package_dir

    def __checkForCanceled(self):
        """
        Check if the task has been canceled.
        """
        if self.__canceled:
            raise PackagePrepareTaskCanceled(self.tr("The task has been canceled."))
