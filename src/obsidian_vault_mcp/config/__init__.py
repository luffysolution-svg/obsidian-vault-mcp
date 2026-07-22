"""Single-file V2 configuration."""

from .defaults import CONFIG_FILENAME, DEFAULT_CONFIG, SCHEMA_VERSION, default_config
from .loader import ConfigLoader, config_path, initialize_config, load_config, save_config
from .schema import CONFIG_SCHEMA, validate_config

__all__ = [
    "CONFIG_FILENAME",
    "CONFIG_SCHEMA",
    "DEFAULT_CONFIG",
    "SCHEMA_VERSION",
    "ConfigLoader",
    "config_path",
    "default_config",
    "initialize_config",
    "load_config",
    "save_config",
    "validate_config",
]
