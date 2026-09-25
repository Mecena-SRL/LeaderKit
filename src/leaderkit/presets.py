"""Caricamento e validazione dei preset JSON.

I preset stanno in file ``*.json`` separati (cartella ``presets/`` del plugin
e cartella utente). Il formato è documentato nel README; ``validate`` fa i
controlli strutturali, ``layout`` quelli che dipendono dal frame rate.
"""

import io
import json
import os

SCHEMA_VERSION = 1

SLATE_FIELDS = ["title", "director", "editor", "colorist", "date", "version",
                "duration", "fps", "resolution"]
# Campi calcolati dal plugin (non si compilano a mano).
AUTO_FIELDS = ["duration", "fps", "resolution"]

HEAD_TYPES = ("slate", "countdown", "pop", "card", "black")
TAIL_TYPES = ("pop", "card", "black", "slate")

MARKER_COLORS = ("Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple",
                 "Fuchsia", "Rose", "Lavender", "Sky", "Mint", "Lemon", "Sand",
                 "Cocoa", "Cream")


class PresetError(ValueError):
    pass


def _require(cond, msg, preset_id):
    if not cond:
        raise PresetError("Preset %s: %s" % (preset_id, msg))


def validate(preset):
    pid = preset.get("id", "?")
    _require(preset.get("schema") == SCHEMA_VERSION,
             "schema deve essere %d" % SCHEMA_VERSION, pid)
    for key in ("id", "name", "ffoa_tc"):
        _require(isinstance(preset.get(key), str) and preset[key].strip(),
                 "campo obbligatorio '%s' mancante" % key, pid)
    _require(isinstance(preset.get("head", []), list), "'head' deve essere una lista", pid)
    _require(isinstance(preset.get("tail", []), list), "'tail' deve essere una lista", pid)
    for section, allowed in (("head", HEAD_TYPES), ("tail", TAIL_TYPES)):
        for i, ev in enumerate(preset.get(section, [])):
            _require(isinstance(ev, dict) and ev.get("type") in allowed,
                     "%s[%d]: type deve essere uno di %s" % (section, i, ", ".join(allowed)), pid)
            t = ev["type"]
            if t == "countdown":
                _require(isinstance(ev.get("from"), int) and isinstance(ev.get("to"), int)
                         and ev["from"] >= ev["to"] >= 1,
                         "%s[%d]: countdown richiede from >= to >= 1" % (section, i), pid)
            elif t == "pop":
                _require("at" in ev, "%s[%d]: pop richiede 'at'" % (section, i), pid)
            else:
                _require("start" in ev and "duration" in ev,
                         "%s[%d]: %s richiede 'start' e 'duration'" % (section, i, t), pid)
    markers = preset.get("markers", {})
    for key in ("ffoa_lfoa", "sync", "interval"):
        cfg = markers.get(key)
        if cfg is not None:
            _require(cfg.get("color", "Blue") in MARKER_COLORS,
                     "markers.%s.color non valido (usa: %s)" % (key, ", ".join(MARKER_COLORS)), pid)
    interval = markers.get("interval")
    if interval:
        _require(interval.get("kind", "reel") in ("reel", "break"),
                 "markers.interval.kind deve essere 'reel' o 'break'", pid)
    slate = preset.get("slate", {})
    for f in slate.get("fields", []):
        _require(f in SLATE_FIELDS, "campo slate sconosciuto '%s'" % f, pid)
    return preset


def load_file(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except ValueError as exc:
            raise PresetError("%s: JSON non valido (%s)" % (os.path.basename(path), exc))
    data["_path"] = path
    return validate(data)


def load_all(directories):
    """Carica i preset da più cartelle; a parità di id vince l'ultima cartella.

    Restituisce (preset ordinati per nome, errori come stringhe).
    """
    found = {}
    errors = []
    for d in directories:
        if not d or not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.lower().endswith(".json"):
                continue
            try:
                p = load_file(os.path.join(d, name))
                found[p["id"]] = p
            except (PresetError, IOError, OSError) as exc:
                errors.append(str(exc))
    return sorted(found.values(), key=lambda p: p["name"].lower()), errors
