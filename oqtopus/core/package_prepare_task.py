import os
import re
import shutil
import zipfile

import requests
from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.module_package import ModulePackage
from ..utils.plugin_utils import PluginUtils, logger


class PackagePrepareTaskCanceled(Exception):
    pass


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be safe for use as a filename/directory name.

    Replaces characters that are problematic on Windows or other filesystems.
    For PR names like "#909 some title", extracts just the number to keep paths short.
    """
    # For PR-style names starting with #, extract just the number
    pr_match = re.match(r"#?(\d+)", name)
    if pr_match:
        return f"PR_{pr_match.group(1)}"

    # Replace characters that are invalid on Windows: < > : " / \\ | ? * #
    # Also replace spaces to avoid path issues
    sanitized = re.sub(r'[<>:"/\\|?*#\s]+', "_", name)
    # Remove leading/trailing underscores and dots
    sanitized = sanitized.strip("_.")
    # Limit length to avoid Windows MAX_PATH issues (260 char limit)
    # Keep it very short since zip contents add more nested paths
    if len(sanitized) > 40:
        sanitized = sanitized[:40]
    return sanitized


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
        This method creates a cache directory for the package downloads.
        """
        # Sanitize the package name to avoid filesystem issues (especially on Windows)
        # PR names can contain special characters like # and spaces
        safe_name = sanitize_filename(self.module_package.name)
        cache_dir = os.path.join(
            PluginUtils.plugin_cache_path(),
            "pkgs",
            self.module_package.organisation,
            self.module_package.repository,
            safe_name,
        )
        os.makedirs(cache_dir, exist_ok=True)

        return cache_dir

    def __prepare_module_assets(self, module_package):

        # Pre-fetch all file sizes to calculate accurate total progress
        self.__prefetch_download_sizes(module_package)

        # Download the source or use from zip
        zip_file = self.from_zip_file or self.__download_module_asset(
            module_package.download_url, "source.zip", module_package
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
                module_package,
            )
            package_dir = self.__extract_zip_file(zip_file)
            module_package.asset_project.package_zip = zip_file
            module_package.asset_project.package_dir = package_dir

        self.__checkForCanceled()
        if module_package.asset_plugin is not None:
            zip_file = self.__download_module_asset(
                module_package.asset_plugin.download_url,
                module_package.asset_plugin.type.value + ".zip",
                module_package,
            )
            package_dir = self.__extract_zip_file(zip_file)
            module_package.asset_plugin.package_zip = zip_file
            module_package.asset_plugin.package_dir = package_dir

    def __prefetch_download_sizes(self, module_package):
        """Pre-fetch Content-Length for all files to be downloaded for accurate progress."""
        logger.debug("Pre-fetching download sizes...")

        urls_to_check = []

        # Check source if not from zip
        if self.from_zip_file is None:
            # Only check if not already cached
            cache_filename = self.__get_cache_filename("source.zip", module_package)
            zip_file = os.path.join(self.__destination_directory, cache_filename)
            if not self.__is_cached_and_valid(zip_file):
                urls_to_check.append((module_package.download_url, "source.zip"))

        # Check project asset
        if module_package.asset_project is not None:
            cache_filename = self.__get_cache_filename(
                module_package.asset_project.type.value + ".zip", module_package
            )
            zip_file = os.path.join(self.__destination_directory, cache_filename)
            if not self.__is_cached_and_valid(zip_file):
                urls_to_check.append(
                    (
                        module_package.asset_project.download_url,
                        module_package.asset_project.type.value + ".zip",
                    )
                )

        # Check plugin asset
        if module_package.asset_plugin is not None:
            cache_filename = self.__get_cache_filename(
                module_package.asset_plugin.type.value + ".zip", module_package
            )
            zip_file = os.path.join(self.__destination_directory, cache_filename)
            if not self.__is_cached_and_valid(zip_file):
                urls_to_check.append(
                    (
                        module_package.asset_plugin.download_url,
                        module_package.asset_plugin.type.value + ".zip",
                    )
                )

        # If everything is cached, skip size checking entirely
        if not urls_to_check:
            logger.debug("All files are cached, skipping size check")
            self.__download_total_expected = 0
            return

        total_size = 0
        for url, filename in urls_to_check:
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

    def __is_cached_and_valid(self, zip_file):
        """Check if a zip file is cached and valid (quick check)."""
        if not os.path.exists(zip_file):
            return False
        # Quick check: file exists and has reasonable size
        try:
            size = os.path.getsize(zip_file)
            if size < 100:  # Too small to be valid
                return False
            # Just check if it opens as a valid zip, don't read entire contents
            with zipfile.ZipFile(zip_file, "r") as zip_test:
                # Quick check - just verify we can read the file list
                _ = zip_test.namelist()
            return True
        except (zipfile.BadZipFile, OSError, Exception):
            return False

    def __get_cache_filename(self, base_filename: str, module_package):
        """Generate cache filename, including commit SHA for branches/PRs if available."""
        if module_package.type in (ModulePackage.Type.BRANCH, ModulePackage.Type.PULL_REQUEST):
            if module_package.commit_sha:
                # Include commit SHA in filename for cache invalidation
                name, ext = os.path.splitext(base_filename)
                return f"{name}-{module_package.commit_sha[:8]}{ext}"
            else:
                # No commit SHA available, don't cache (use unique name)
                import time

                name, ext = os.path.splitext(base_filename)
                return f"{name}-{int(time.time())}{ext}"
        return base_filename

    def __download_module_asset(self, url: str, filename: str, module_package):

        cache_filename = self.__get_cache_filename(filename, module_package)
        zip_file = os.path.join(self.__destination_directory, cache_filename)

        # Check if file already exists and is valid
        if os.path.exists(zip_file):
            try:
                # Quick validation - just check if it's a valid zip structure
                file_size = os.path.getsize(zip_file)
                if file_size > 100:  # Has reasonable size
                    with zipfile.ZipFile(zip_file, "r") as zip_test:
                        # Just verify we can read file list, don't test entire contents
                        _ = zip_test.namelist()
                    logger.info(
                        f"File '{zip_file}' already exists and is valid - skipping download"
                    )
                    # Still emit some progress to show we're not stuck
                    logger.debug(
                        f"Returning from cache: expected={self.__download_total_expected}, received={self.__download_total_received}"
                    )
                    self.signalPackagingProgress.emit(-1.0, 0)
                    return zip_file
            except (zipfile.BadZipFile, OSError, Exception) as e:
                logger.warning(f"Existing file '{zip_file}' is invalid ({e}), will re-download")
                try:
                    os.remove(zip_file)
                except OSError:
                    pass

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
        # Don't set indeterminate here - it confuses the progress when downloading multiple files

        try:
            with zipfile.ZipFile(zip_file, "r") as zip_ref:
                # Find the top-level directory in the zip
                zip_dirname = zip_ref.namelist()[0].split("/")[0]

                # Use short "src" name to avoid Windows MAX_PATH issues
                package_dir = os.path.join(self.__destination_directory, "src")

                # Check if already extracted and valid
                if os.path.exists(package_dir) and os.path.isdir(package_dir):
                    # Verify it's not empty and has some expected content
                    if os.listdir(package_dir):
                        logger.info(
                            f"Directory '{package_dir}' already extracted - skipping extraction"
                        )
                        return package_dir
                    else:
                        logger.warning(f"Directory '{package_dir}' is empty, will re-extract")
                        shutil.rmtree(package_dir)

                logger.info(f"Extracting '{zip_file}'...")
                zip_ref.extractall(self.__destination_directory)

                # Rename extracted dir to "src" to shorten paths
                extracted_dir = os.path.join(self.__destination_directory, zip_dirname)
                if extracted_dir != package_dir:
                    shutil.move(extracted_dir, package_dir)

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
