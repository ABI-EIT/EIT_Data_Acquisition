import yaml
import json
import os
import pathlib
from copy import deepcopy


class Config:
    """
        A class to manage a configuration dict.
        Load safely loads the config from file, using default values if necessary
        Save safely saves the internal config dict to file
    """
    def __init__(self, path, default=None, type="json"):
        if default is None:
            default = {}
        if type != "yaml" and type != "json":
            raise ValueError("Config type must be yaml or json")
        self.type = type
        self.default_config = default
        self.config = default
        self.path = path
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                if self.type == "yaml":
                    self.config = yaml.safe_load(f)
                else:
                    self.config = json.load(f)

        else:
            self.config = self.default_config
            self.save()

    def save(self):
        pathlib.Path(self.path).parent.mkdir(parents=True, exist_ok=True)

        with open(self.path, "w") as f:
            if self.type == "yaml":
                yaml.safe_dump(self.config, f, width=1000)
            else:
                json.dump(self.config, f, indent=4)

    def __getitem__(self, key):
        return self.config[key]

    def __setitem__(self, key, value):
        self.config[key] = value

    def __contains__(self, item):
        return item in self.config

