"""LeaderKit — voce di menu Workspace > Scripts > LeaderKit.

Script d'ingresso installato in .../Fusion/Scripts/Utility/. La libreria sta
in .../Fusion/LeaderKit/ (vedi README).
"""

import os
import sys


def _candidates():
    env = os.environ.get("LEADERKIT_HOME")
    if env:
        yield env
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        yield os.path.join(here, "..", "..", "LeaderKit")   # Fusion/Scripts/Utility -> Fusion/LeaderKit
        yield here                                          # checkout di sviluppo (src/)
    except NameError:
        pass
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        yield os.path.join(home, "Library", "Application Support", "Blackmagic Design",
                           "DaVinci Resolve", "Fusion", "LeaderKit")
    elif sys.platform.startswith("win"):
        yield os.path.join(os.environ.get("APPDATA", ""), "Blackmagic Design",
                           "DaVinci Resolve", "Support", "Fusion", "LeaderKit")
    else:
        yield os.path.join(home, ".local", "share", "DaVinciResolve", "Fusion", "LeaderKit")


def _bootstrap():
    for path in _candidates():
        path = os.path.abspath(path)
        if os.path.isdir(os.path.join(path, "leaderkit")):
            if path not in sys.path:
                sys.path.insert(0, path)
            return path
    raise ImportError("Libreria LeaderKit non trovata: reinstalla il plugin")


def _host():
    g = globals()
    res = g.get("resolve")
    fu = g.get("fusion") or g.get("fu")
    bmd = g.get("bmd")
    if res is None or bmd is None:
        try:
            import DaVinciResolveScript as dvr
            bmd = bmd or dvr
            res = res or dvr.scriptapp("Resolve")
        except ImportError:
            pass
    if res is not None and fu is None:
        try:
            fu = res.Fusion()
        except Exception:
            fu = None
    return res, fu, bmd


_bootstrap()
from leaderkit import ui  # noqa: E402

_resolve, _fusion, _bmd = _host()
if _resolve is None:
    print("LeaderKit: avvia lo script da DaVinci Resolve (Workspace > Scripts > LeaderKit)")
else:
    ui.main(_resolve, _fusion, _bmd)
