import json
import os
import re
import time

from qgis.PyQt.QtCore import (
    QByteArray,
    QObject,
    QTimer,
    QUrl,
    pyqtSignal,
)
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from ..utils.plugin_utils import PluginUtils, logger
from .module_package import ModulePackage

# Cache duration in seconds (1 hour)
CACHE_DURATION = 3600


class Module(QObject):
    signal_versionsLoaded = pyqtSignal(str)
    signal_developmentVersionsLoaded = pyqtSignal(str)

    def __init__(
        self,
        name: str,
        id: str,
        organisation: str,
        repository: str,
        exclude_releases: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.name = name
        self.id = id
        self.organisation = organisation
        self.repository = repository
        self.exclude_releases = exclude_releases
        self.versions = []
        self.development_versions = []
        self.latest_version = None
        self.network_manager = QNetworkAccessManager(self)

    def __repr__(self):
        return f"Module(name={self.name}, organisation={self.organisation}, repository={self.repository})"

    def __get_cache_dir(self):
        """Get the cache directory for GitHub API responses."""
        cache_dir = os.path.join(
            PluginUtils.plugin_cache_path(), "github_api", self.organisation, self.repository
        )
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def __get_cache_file(self, cache_type):
        """Get the cache file path for a specific type (releases or pulls)."""
        cache_file = os.path.join(self.__get_cache_dir(), f"{cache_type}.json")
        return cache_file

    def __read_cache(self, cache_type):
        """Read cached data if it exists and is not expired."""
        cache_file = self.__get_cache_file(cache_type)
        if not os.path.exists(cache_file):
            return None

        # Check if cache is expired
        file_age = time.time() - os.path.getmtime(cache_file)
        if file_age > CACHE_DURATION:
            return None

        try:
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
                logger.info(
                    f"Using cached {cache_type} data (age: {file_age:.0f}s, {len(data)} items)"
                )
                return data
        except Exception as e:
            logger.warning(f"Failed to read cache for {cache_type}: {e}")
            return None

    def __write_cache(self, cache_type, data):
        """Write data to cache file."""
        cache_file = self.__get_cache_file(cache_type)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to write cache for {cache_type}: {e}")

    def start_load_versions(self):
        # Read cache asynchronously to avoid blocking UI
        QTimer.singleShot(0, self.__async_load_versions)

    def __async_load_versions(self):
        """Load versions asynchronously from cache or API."""
        # Try to load from cache first
        cached_data = self.__read_cache("releases")
        if cached_data is not None:
            try:
                self._process_versions_data(cached_data)
                self.signal_versionsLoaded.emit("")
                return
            except Exception as e:
                logger.warning(f"Failed to process cached releases: {e}")

        # Cache miss or invalid - fetch from API
        url = f"https://api.github.com/repos/{self.organisation}/{self.repository}/releases"
        logger.info(f"Loading versions from '{url}'...")
        request = QNetworkRequest(QUrl(url))
        headers = PluginUtils.get_github_headers()
        for key, value in headers.items():
            request.setRawHeader(QByteArray(key.encode()), QByteArray(value.encode()))
        reply = self.network_manager.get(request)
        reply.finished.connect(lambda: self._on_versions_reply(reply))

    def _on_versions_reply(self, reply):
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.signal_versionsLoaded.emit(reply.errorString())
            reply.deleteLater()
            return
        try:
            data = reply.readAll().data()
            json_versions = json.loads(data.decode())

            # Cache the response
            self.__write_cache("releases", json_versions)

            self._process_versions_data(json_versions)
            self.signal_versionsLoaded.emit("")
        except Exception as e:
            self.signal_versionsLoaded.emit(str(e))
        reply.deleteLater()

    def _process_versions_data(self, json_versions):
        """Process versions data from cache or API response."""
        self.versions = []
        self.latest_version = None

        # Compile exclude pattern if specified
        exclude_pattern = None
        if self.exclude_releases:
            try:
                exclude_pattern = re.compile(self.exclude_releases)
            except re.error as e:
                logger.warning(f"Invalid exclude_releases pattern '{self.exclude_releases}': {e}")

        for json_version in json_versions:
            # Check if this release should be excluded
            tag_name = json_version.get("tag_name", "")
            if exclude_pattern and exclude_pattern.search(tag_name):
                continue

            module_package = ModulePackage(
                module=self,
                organisation=self.organisation,
                repository=self.repository,
                json_payload=json_version,
                type=ModulePackage.Type.RELEASE,
            )
            self.versions.append(module_package)

            # Latest version -> most recent commit date for non prerelease
            if module_package.prerelease is True:
                continue

            if self.latest_version is None:
                self.latest_version = module_package
                continue

            if module_package.created_at > self.latest_version.created_at:
                self.latest_version = module_package

    def start_load_development_versions(self):
        self.development_versions = []

        # Add pre-releases from already loaded versions
        for version in self.versions:
            if version.prerelease is True:
                self.development_versions.append(version)

        # Create version for the main branch
        mainVersion = ModulePackage(
            module=self,
            organisation=self.organisation,
            repository=self.repository,
            json_payload="",
            type=ModulePackage.Type.BRANCH,
            name="main",
            branch="main",
        )
        # Fetch the latest commit SHA for caching (async to avoid blocking UI)
        QTimer.singleShot(0, lambda: mainVersion.fetch_commit_sha())
        self.development_versions.append(mainVersion)

        # Try to load pull requests from cache first
        cached_data = self.__read_cache("pulls")
        if cached_data is not None:
            # Process cache asynchronously to keep UI responsive
            QTimer.singleShot(0, lambda: self._process_cached_pulls(cached_data))
            return

        # Cache miss or invalid - fetch from API
        url = f"https://api.github.com/repos/{self.organisation}/{self.repository}/pulls"
        logger.info(f"Loading pre-releases and development versions from '{url}'...")

        request = QNetworkRequest(QUrl(url))
        headers = PluginUtils.get_github_headers()
        for key, value in headers.items():
            request.setRawHeader(QByteArray(key.encode()), QByteArray(value.encode()))
        reply = self.network_manager.get(request)
        reply.finished.connect(lambda: self._on_development_versions_reply(reply))

    def _process_cached_pulls(self, cached_data):
        """Process cached pull requests data asynchronously."""
        try:
            self._process_pull_requests_data(cached_data)
            self.signal_developmentVersionsLoaded.emit("")
        except Exception as e:
            logger.warning(f"Failed to process cached pull requests: {e}")
            # On error, continue with API call
            url = f"https://api.github.com/repos/{self.organisation}/{self.repository}/pulls"
            logger.info(f"Loading pre-releases and development versions from '{url}'...")
            request = QNetworkRequest(QUrl(url))
            headers = PluginUtils.get_github_headers()
            for key, value in headers.items():
                request.setRawHeader(QByteArray(key.encode()), QByteArray(value.encode()))
            reply = self.network_manager.get(request)
            reply.finished.connect(lambda: self._on_development_versions_reply(reply))

    def _on_development_versions_reply(self, reply):
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.signal_developmentVersionsLoaded.emit(reply.errorString())
            reply.deleteLater()
            return

        try:
            data = reply.readAll().data()
            json_versions = json.loads(data.decode())

            # Cache the response
            self.__write_cache("pulls", json_versions)

            self._process_pull_requests_data(json_versions)
            self.signal_developmentVersionsLoaded.emit("")
        except Exception as e:
            self.signal_developmentVersionsLoaded.emit(str(e))
        reply.deleteLater()

    def _process_pull_requests_data(self, json_versions):
        """Process pull requests data from cache or API response."""
        for json_version in json_versions:
            module_package = ModulePackage(
                module=self,
                organisation=self.organisation,
                repository=self.repository,
                json_payload=json_version,
                type=ModulePackage.Type.PULL_REQUEST,
            )
            self.development_versions.append(module_package)
