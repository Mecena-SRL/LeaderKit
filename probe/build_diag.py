#!/usr/bin/env python3
"""Pacchetto diagnostico: varianti del LeaderKit Head per capire perché Resolve
non lo mostra. Ogni variante è un generatore separato; quelle che compaiono
nella libreria Effetti indicano cosa funziona.

    python3 probe/build_diag.py  ->  dist/LeaderKit-Diagnostica.drfx
"""

import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import build_fx  # noqa: E402
import build_v3  # noqa: E402


def rename(text, old_id, new_id):
    return text.replace(old_id + " = ", new_id + " = ", 1).replace(
        'ActiveTool = "%s"' % old_id, 'ActiveTool = "%s"' % new_id)


def strip_buttons(text):
    text = re.sub(r'\t+(Generate|Remove) = \{ LINKID_DataType = "Number", INPID_InputControl = "ButtonControl".*\n', "", text)
    return re.sub(r'\t+Input\d+ = InstanceInput \{ SourceOp = "LK", Source = "(Generate|Remove)", \},\n', "", text)


def variants():
    head, tail = build_fx.head(), build_fx.tail()
    minimal = dict(build_v3.tests())["A"]
    return [
        ("LKD1 Gruppo minimo", rename(minimal, "LK3TestA", "LKD1")),
        ("LKD2 Coda", rename(tail, "LeaderKitTail", "LKD2")),
        ("LKD3 Head senza bottoni", rename(strip_buttons(head), "LeaderKitHead", "LKD3")),
        ("LKD4 Head completo", rename(head, "LeaderKitHead", "LKD4")),
        ("LKD5 Head come Macro", rename(head.replace("= GroupOperator {", "= MacroOperator {", 1),
                                        "LeaderKitHead", "LKD5")),
    ]


def build():
    path = os.path.join(ROOT, "dist", "LeaderKit-Diagnostica.drfx")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in variants():
            zf.writestr("Edit/Generators/LeaderKit Diagnostica/%s.setting" % name, text)
            with open(os.path.join(ROOT, "dist", name + ".setting"), "w") as fh:
                fh.write(text)
    return path


if __name__ == "__main__":
    print(build())
