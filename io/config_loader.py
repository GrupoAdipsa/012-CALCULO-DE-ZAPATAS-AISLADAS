"""
io/config_loader.py
Load and save project configuration from JSON / YAML files.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict


def load_json_config(filepath: str) -> Dict[str, Any]:
    """
    Load configuration from a JSON file.

    Parameters
    ----------
    filepath : path to .json file

    Returns
    -------
    dict with configuration data
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_yaml_config(filepath: str) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.

    Parameters
    ----------
    filepath : path to .yaml / .yml file

    Returns
    -------
    dict with configuration data
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required for YAML config loading.")

    with open(filepath, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def save_config(config: Dict[str, Any], filepath: str) -> None:
    """
    Save configuration dict to a file.
    File format is determined by extension (.json / .yaml / .yml).

    Parameters
    ----------
    config   : dictionary to save
    filepath : destination file path
    """
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".json":
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=2, ensure_ascii=False)
    elif ext in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required for YAML config saving.")
        with open(filepath, "w", encoding="utf-8") as fh:
            yaml.dump(config, fh, allow_unicode=True, default_flow_style=False)
    else:
        raise ValueError(
            f"Unsupported file extension '{ext}'. Use .json, .yaml, or .yml."
        )
