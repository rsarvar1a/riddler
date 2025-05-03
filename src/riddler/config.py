import dataclasses
import tomllib
import typing

@dataclasses.dataclass
class Config:
    home_guild: int
    log_level: str
    owners: typing.List[int]
    prefix: str

    def __init__(self, home_guild: int, log_level: str, owners: typing.List[int], prefix: str):
        self.home_guild = home_guild
        self.log_level = log_level
        self.owners = owners
        self.prefix = prefix
    
    @classmethod
    def load(cls, path):
        with open(path, 'rb') as toml_file:
            obj = tomllib.load(toml_file)
        return Config(**obj)
