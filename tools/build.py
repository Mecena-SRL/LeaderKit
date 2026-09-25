#!/usr/bin/env python3
"""Build dei pacchetti LeaderKit.

    python3 tools/build.py            # dist/: .drfx, .zip multipiattaforma, .dmg (se possibile)

Il .dmg viene creato con ``hdiutil`` su macOS (UDZO compresso) oppure, su
Linux, con ``genisoimage`` (immagine ISO9660 + Rock Ridge che macOS monta come
disco e che conserva i permessi di esecuzione dell'installer).
"""

import os
import shutil
import stat
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from leaderkit import __version__, fusion, presets  # noqa: E402

DIST = os.path.join(ROOT, "dist")
FIXED_DATE = (2026, 1, 1, 0, 0, 0)  # zip riproducibili


def _zip_write(zf, arcname, data, executable=False):
    info = zipfile.ZipInfo(arcname, FIXED_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = ((0o755 if executable else 0o644) | stat.S_IFREG) << 16
    zf.writestr(info, data)


def build_drfx(path):
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in fusion.drfx_templates().items():
            _zip_write(zf, "Edit/Titles/LeaderKit/" + name, text.encode("utf-8"))
    return path


def build_payload(stage):
    """stage/payload/{Scripts/Utility/LeaderKit.py, LeaderKit/{leaderkit,presets}}"""
    payload = os.path.join(stage, "payload")
    lib = os.path.join(payload, "LeaderKit")
    os.makedirs(os.path.join(payload, "Scripts", "Utility"))
    shutil.copy2(os.path.join(ROOT, "src", "LeaderKit.py"),
                 os.path.join(payload, "Scripts", "Utility", "LeaderKit.py"))
    shutil.copytree(os.path.join(ROOT, "src", "leaderkit"), os.path.join(lib, "leaderkit"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    os.makedirs(os.path.join(lib, "presets"))
    for name in sorted(os.listdir(os.path.join(ROOT, "presets"))):
        if name.endswith(".json"):
            presets.load_file(os.path.join(ROOT, "presets", name))  # fallisce se non valido
            shutil.copy2(os.path.join(ROOT, "presets", name), os.path.join(lib, "presets", name))
    with open(os.path.join(lib, "VERSION"), "w") as fh:
        fh.write(__version__ + "\n")


def _readme_txt():
    return (
        "LeaderKit %s — plugin per DaVinci Resolve 20+\n\n"
        "INSTALLAZIONE\n"
        "  macOS:   doppio clic su 'Installa LeaderKit.command'\n"
        "           (se macOS blocca il file: tasto destro > Apri, oppure da Terminale:\n"
        "            bash \"/Volumes/LeaderKit/Installa LeaderKit.command\")\n"
        "  Linux:   bash install.sh\n"
        "  Windows: doppio clic su install.bat (non ancora testato)\n\n"
        "Poi riavvia Resolve e apri Workspace > Scripts > LeaderKit.\n"
        "Requisito: Python 3 installato nel sistema (richiesto da Resolve per gli script Python).\n\n"
        "LeaderKit.drfx contiene solo i title template (Edit > Titles > LeaderKit);\n"
        "l'installer lo copia già nella cartella Templates di Fusion.\n\n"
        "Disinstallazione: 'Disinstalla LeaderKit.command' (macOS) o install.sh --uninstall.\n"
    ) % __version__


def stage_common(stage):
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    build_payload(stage)
    shutil.copy2(os.path.join(DIST, "LeaderKit.drfx"), os.path.join(stage, "LeaderKit.drfx"))
    with open(os.path.join(stage, "LEGGIMI.txt"), "w", encoding="utf-8") as fh:
        fh.write(_readme_txt())


def _exec_copy(src, dst):
    shutil.copy2(src, dst)
    os.chmod(dst, 0o755)


def build_zip(path):
    stage = os.path.join(DIST, "_stage_zip", "LeaderKit")
    stage_common(stage)
    _exec_copy(os.path.join(ROOT, "installer", "install.sh"), os.path.join(stage, "install.sh"))
    shutil.copy2(os.path.join(ROOT, "installer", "windows", "install.bat"),
                 os.path.join(stage, "install.bat"))
    base = os.path.dirname(stage)
    with zipfile.ZipFile(path, "w") as zf:
        for folder, _, files in sorted(os.walk(stage)):
            for name in sorted(files):
                full = os.path.join(folder, name)
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                with open(full, "rb") as fh:
                    _zip_write(zf, rel, fh.read(), os.access(full, os.X_OK))
    shutil.rmtree(base)
    return path


def build_dmg(path):
    stage = os.path.join(DIST, "_stage_dmg")
    stage_common(stage)
    _exec_copy(os.path.join(ROOT, "installer", "install.sh"),
               os.path.join(stage, "Installa LeaderKit.command"))
    uninstall = os.path.join(stage, "Disinstalla LeaderKit.command")
    with open(uninstall, "w") as fh:
        fh.write('#!/bin/bash\nexec bash "$(dirname "$0")/Installa LeaderKit.command" --uninstall\n')
    os.chmod(uninstall, 0o755)
    if os.path.exists(path):
        os.remove(path)
    try:
        if shutil.which("hdiutil"):
            subprocess.check_call(["hdiutil", "create", "-volname", "LeaderKit", "-srcfolder",
                                   stage, "-ov", "-format", "UDZO", path])
        elif shutil.which("genisoimage") or shutil.which("mkisofs"):
            tool = shutil.which("genisoimage") or shutil.which("mkisofs")
            subprocess.check_call([tool, "-quiet", "-V", "LeaderKit", "-D", "-R", "-J",
                                   "-joliet-long", "-no-pad", "-o", path, stage])
        else:
            print("dmg saltato: servono hdiutil (macOS) o genisoimage (Linux)")
            return None
    finally:
        shutil.rmtree(stage)
    return path


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    outputs = [build_drfx(os.path.join(DIST, "LeaderKit.drfx"))]
    outputs.append(build_zip(os.path.join(DIST, "LeaderKit-%s.zip" % __version__)))
    outputs.append(build_dmg(os.path.join(DIST, "LeaderKit-%s-macOS.dmg" % __version__)))
    for out in outputs:
        if out:
            print("%-40s %8d byte" % (os.path.relpath(out, ROOT), os.path.getsize(out)))


if __name__ == "__main__":
    main()
