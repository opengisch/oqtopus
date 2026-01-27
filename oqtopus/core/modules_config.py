from pydantic import BaseModel


class ModuleConfig(BaseModel):
    name: str
    id: str
    organisation: str
    repository: str


class ModulesConfig(BaseModel):
    modules: list[ModuleConfig]
