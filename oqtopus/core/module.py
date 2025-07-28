import json

from qgis.PyQt.QtCore import QByteArray, QObject, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from ..utils.plugin_utils import PluginUtils, logger
from .module_package import ModulePackage


class Module(QObject):
    signal_versionsLoaded = pyqtSignal(str)
    signal_developmentVersionsLoaded = pyqtSignal(str)

    def __init__(self, name: str, organisation: str, repository: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.organisation = organisation
        self.repository = repository
        self.versions = []
        self.development_versions = []
        self.latest_version = None
        self.network_manager = QNetworkAccessManager(self)

    def __repr__(self):
        return f"Module(name={self.name}, organisation={self.organisation}, repository={self.repository})"

    def start_load_versions(self):
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
            self.versions = []
            self.latest_version = None
            for json_version in json_versions:
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
            self.signal_versionsLoaded.emit("")
        except Exception as e:
            self.signal_versionsLoaded.emit(str(e))
        reply.deleteLater()

    def start_load_development_versions(self):
        self.development_versions = []

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
        self.development_versions.append(mainVersion)

        url = f"https://api.github.com/repos/{self.organisation}/{self.repository}/pulls"
        logger.info(f"Loading development versions from '{url}'...")

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
            for json_version in json_versions:
                module_package = ModulePackage(
                    module=self,
                    organisation=self.organisation,
                    repository=self.repository,
                    json_payload=json_version,
                    type=ModulePackage.Type.PULL_REQUEST,
                )
                self.development_versions.append(module_package)
            self.signal_developmentVersionsLoaded.emit("")
        except Exception as e:
            self.signal_developmentVersionsLoaded.emit(str(e))
        reply.deleteLater()
