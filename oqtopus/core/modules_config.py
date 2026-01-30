from pydantic import BaseModel


class ModuleConfig(BaseModel):
    name: str
    id: str
    organisation: str
    repository: str
    exclude_releases: str | None = None  # Regexp pattern to exclude releases


class ModulesConfig(BaseModel):
    modules: list[ModuleConfig]
