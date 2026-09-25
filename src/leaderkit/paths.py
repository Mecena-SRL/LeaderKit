"""Percorsi di installazione e cache, per sistema operativo."""

import os
import sys


def fusion_user_dir():
    """Cartella utente di Fusion dentro Resolve (Scripts/, Templates/...)."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "Blackmagic Design",
                            "DaVinci Resolve", "Fusion")
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
        return os.path.join(appdata, "Blackmagic Design", "DaVinci Resolve", "Support", "Fusion")
    return os.path.join(home, ".local", "share", "DaVinciResolve", "Fusion")


def install_dir():
    """Cartella LeaderKit (libreria + preset di fabbrica)."""
    return os.path.join(fusion_user_dir(), "LeaderKit")


def package_root():
    """Radice del pacchetto installato o del checkout (contiene presets/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
        if os.path.isdir(os.path.join(candidate, "presets")):
            return candidate
    return install_dir()


def factory_presets_dir():
    return os.path.join(package_root(), "presets")


def user_presets_dir():
    return os.path.join(install_dir(), "presets-user")


def cache_dir():
    base = os.environ.get("LEADERKIT_CACHE")
    if base:
        return base
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Caches", "LeaderKit")
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(local, "LeaderKit", "cache")
    return os.path.join(os.path.expanduser("~"), ".cache", "LeaderKit")


def settings_file():
    return os.path.join(install_dir(), "last-values.json")
