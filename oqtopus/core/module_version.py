import requests
from qgis.PyQt.QtCore import QDateTime, Qt

from ..utils.plugin_utils import PluginUtils
from .module_asset import ModuleAsset


class ModuleVersion:

    # enum for version type
    class Type:
        RELEASE = "release"
        BRANCH = "branch"
        PULL_REQUEST = "pull_request"
        FROM_ZIP = "from_zip"

    def __init__(
        self,
        organisation,
        repository,
        json_payload: dict,
        type=Type.RELEASE,
        name=None,
        branch=None,
    ):

        self.type = type
        self.name = name
        self.branch = branch
        self.created_at = None
        self.prerelease = False
        self.html_url = None

        self.asset_datamodel = None
        self.asset_project = None
        self.asset_plugin = None

        if self.type == ModuleVersion.Type.RELEASE:
            self.__parse_release(json_payload)
        elif self.type == ModuleVersion.Type.BRANCH:
            pass
        elif self.type == ModuleVersion.Type.PULL_REQUEST:
            self.__parse_pull_request(json_payload)
        elif self.type == ModuleVersion.Type.FROM_ZIP:
            return
        else:
            raise ValueError(f"Unknown type '{type}'")

        type = "heads"
        if self.type == ModuleVersion.Type.RELEASE:
            type = "tags"

        self.download_url = (
            f"https://github.com/{organisation}/{repository}/archive/refs/{type}/{self.branch}.zip"
        )

        self.package_dir = None

    def display_name(self):
        if self.prerelease:
            return f"{self.name} (prerelease)"

        return self.name

    def __parse_release(self, json_payload: dict):
        if self.name is None:
            self.name = json_payload["name"]

        if self.name is None or self.name == "":
            self.name = json_payload["tag_name"]

        self.branch = self.name
        self.created_at = QDateTime.fromString(json_payload["created_at"], Qt.DateFormat.ISODate)
        self.prerelease = json_payload["prerelease"]
        self.html_url = json_payload["html_url"]

        self.__parse_release_assets(json_payload["assets_url"])

    def __parse_release_assets(self, assets_url: str):

        # Load assets
        r = requests.get(assets_url, headers=PluginUtils.get_github_headers())

        # Raise an exception in case of http errors
        r.raise_for_status()

        json_assets = r.json()
        for json_asset in json_assets:
            asset = ModuleAsset(
                name=json_asset["name"],
                label=json_asset["label"],
                download_url=json_asset["browser_download_url"],
                size=json_asset["size"],
                type=None,
            )

            if asset.label == ModuleAsset.Type.DATAMODEL.value:
                asset.type = ModuleAsset.Type.DATAMODEL
                self.asset_datamodel = asset
                continue

            if asset.label == ModuleAsset.Type.PROJECT.value:
                asset.type = ModuleAsset.Type.PROJECT
                self.asset_project = asset
                continue

            if asset.label == ModuleAsset.Type.PLUGIN.value:
                asset.type = ModuleAsset.Type.PLUGIN
                self.asset_plugin = asset
                continue

            if self.asset_datamodel and self.asset_project and self.asset_plugin:
                # We already have all assets we need
                break

    def __parse_pull_request(self, json_payload: dict):
        if self.name is None:
            self.name = f"#{json_payload['number']} {json_payload['title']}"
        self.branch = json_payload["head"]["ref"]
        self.created_at = QDateTime.fromString(json_payload["created_at"], Qt.DateFormat.ISODate)
        self.prerelease = False
        self.html_url = json_payload["html_url"]
