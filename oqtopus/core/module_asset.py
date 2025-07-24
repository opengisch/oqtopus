from enum import Enum


class ModuleAsset:
    class Type(Enum):
        PLUGIN = "oqtopus.plugin"
        PROJECT = "oqtopus.project"

    def __init__(
        self, name: str, label: str, download_url: str, size: int, type: "ModuleAsset.Type" = None
    ):
        self.name = name
        self.label = label
        self.download_url = download_url
        self.size = size
        self.type = type
        self.package_zip = None
        self.package_dir = None
