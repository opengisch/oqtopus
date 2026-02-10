from pydantic import BaseModel


class ModuleConfig(BaseModel):
    name: str
    id: str
    organisation: str
    repository: str
    exclude_releases: str | None = None  # Regexp pattern to exclude releases
    experimental: bool = False  # Whether this module is experimental


class ModulesConfig(BaseModel):
    modules: list[ModuleConfig]
