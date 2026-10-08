"""Veroku configurator: first-run terminal config."""

import getpass
import json
import os
import sys


def wizard_config(root: str) -> dict:
    """Interactive first-run configuration in the terminal."""
    print("Welcome to Veroku!")

    while prefix := input("Command prefix [default '.']: ").strip():
        if len(prefix) == 1:
            break
        print("Prefix must be a single character")

    prefix = prefix or "."

    print("Enter owner VK id (your numeric id, e.g. 835360262):")
    while owner := input("> ").strip():
        if owner.isdigit():
            break
        print("Invalid id")

    if not owner:
        print("Cancelled")
        sys.exit(0)

    path = os.path.join(root, "config.json")
    cfg = {"prefix": prefix, "owner": int(owner)}
    with open(path, "w") as f:
        json.dump(cfg, f)
    print(f"Completed! Config saved to {path}")
    return cfg
