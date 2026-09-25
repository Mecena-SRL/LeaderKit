"""Pannello minimo (UIManager di Fusion): preset, campi slate, marker."""

import datetime
import io
import json
import os
import traceback

from . import __version__, paths, presets, resolve_ops
from .layout import LayoutError
from .timecode import TimecodeError

MODES = [("new_timeline", "Nuova timeline di consegna (programma annidato)"),
         ("in_place", "Timeline corrente (serve spazio prima del primo clip)")]
MARKER_KINDS = [("reel", "Fine rullo"), ("break", "Break")]
SLATE_INPUTS = [("title", "Titolo"), ("director", "Regia"), ("editor", "Montaggio"),
                ("colorist", "Color"), ("date", "Data"), ("version", "Versione")]
NO_TARGET = "— nessuno —"


def load_values():
    try:
        with io.open(paths.settings_file(), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (IOError, OSError, ValueError):
        return {}


def save_values(values):
    try:
        folder = os.path.dirname(paths.settings_file())
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with io.open(paths.settings_file(), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(values, ensure_ascii=False, indent=2))
    except (IOError, OSError):
        pass


def load_presets():
    return presets.load_all([paths.factory_presets_dir(), paths.user_presets_dir()])


def run_headless(resolve, log=print):
    """Senza UIManager: usa gli ultimi valori salvati (o i default)."""
    found, errors = load_presets()
    for e in errors:
        log("Preset ignorato: " + e)
    values = load_values()
    by_id = dict((p["id"], p) for p in found)
    preset = by_id.get(values.get("preset")) or (found[0] if found else None)
    if preset is None:
        log("Nessun preset trovato in " + paths.factory_presets_dir())
        return None
    return resolve_ops.generate(resolve, preset, values.get("slate", {}),
                                values.get("options", {}), log)


def main(resolve, fusion, bmd):
    ui = getattr(fusion, "UIManager", None) if fusion else None
    if ui is None or bmd is None:
        print("LeaderKit: UIManager non disponibile, uso gli ultimi valori salvati")
        return run_headless(resolve)
    disp = bmd.UIDispatcher(ui)
    found, errors = load_presets()
    values = load_values()

    def row(label, widget, weight=0.3):
        return ui.HGroup({"Weight": 0}, [ui.Label({"Text": label, "Weight": weight}), widget])

    slate_rows = [row(label, ui.LineEdit({"ID": "S_" + key, "Weight": 1 - 0.3}))
                  for key, label in SLATE_INPUTS]
    win = disp.AddWindow({"ID": "LeaderKitWin", "WindowTitle": "LeaderKit %s" % __version__,
                          "Geometry": [120, 120, 560, 760]}, [
        ui.VGroup({"Spacing": 6}, [
            row("Preset", ui.ComboBox({"ID": "Preset", "Weight": 0.7})),
            ui.Label({"ID": "Desc", "Text": "", "WordWrap": True, "Weight": 0}),
            ui.Label({"ID": "Info", "Text": "", "WordWrap": True, "Weight": 0}),
            row("Modalità", ui.ComboBox({"ID": "Mode", "Weight": 0.7})),
            ui.HGroup({"Weight": 0}, [
                ui.CheckBox({"ID": "Head", "Text": "Testa (slate/countdown/pop)", "Checked": True}),
                ui.CheckBox({"ID": "Tail", "Text": "Coda", "Checked": True}),
                ui.Label({"Text": "Rullo", "Weight": 0}),
                ui.SpinBox({"ID": "Reel", "Minimum": 1, "Maximum": 23, "Value": 1}),
            ]),
            ui.Label({"Text": "<b>Slate</b> (durata, fps e risoluzione sono calcolati)",
                      "Weight": 0}),
        ] + slate_rows + [
            ui.Label({"Text": "<b>Marker</b>", "Weight": 0}),
            ui.HGroup({"Weight": 0}, [
                ui.CheckBox({"ID": "Markers", "Text": "A intervalli", "Checked": False}),
                ui.ComboBox({"ID": "MarkerKind"}),
                ui.Label({"Text": "ogni", "Weight": 0}),
                ui.LineEdit({"ID": "MarkerEvery", "Text": "20m",
                             "PlaceholderText": "es. 20m, 11m6s, 9m"}),
            ]),
            row("Durata target", ui.ComboBox({"ID": "Target", "Weight": 0.7})),
            ui.HGroup({"Weight": 0}, [
                ui.Button({"ID": "Generate", "Text": "Genera"}),
                ui.Button({"ID": "Remove", "Text": "Rimuovi LeaderKit dalla timeline"}),
                ui.Button({"ID": "Close", "Text": "Chiudi"}),
            ]),
            ui.TextEdit({"ID": "Log", "ReadOnly": True, "Weight": 1}),
        ]),
    ])
    items = win.GetItems()
    log_lines = []

    def log(msg):
        log_lines.append(str(msg))
        items["Log"].PlainText = "\n".join(log_lines[-400:])

    for e in errors:
        log("Preset ignorato: " + e)
    if not found:
        log("Nessun preset trovato in %s" % paths.factory_presets_dir())
    items["Preset"].AddItems([p["name"] for p in found])
    items["Mode"].AddItems([label for _, label in MODES])
    items["MarkerKind"].AddItems([label for _, label in MARKER_KINDS])

    def current_preset():
        i = items["Preset"].CurrentIndex
        return found[i] if 0 <= i < len(found) else None

    def timeline_info():
        try:
            project = resolve.GetProjectManager().GetCurrentProject()
            tl = project.GetCurrentTimeline() if project else None
            if not tl:
                return "Nessuna timeline attiva"
            rate, w, h = resolve_ops.timeline_format(project, tl)
            return "Timeline: %s — %s, %d × %d" % (tl.GetName(), rate.label(), w, h)
        except Exception as exc:
            return "Timeline non leggibile: %s" % exc

    def on_preset(ev=None):
        p = current_preset()
        if not p:
            return
        items["Desc"].Text = p.get("description", "")
        interval = p.get("markers", {}).get("interval", {})
        items["Markers"].Checked = bool(interval.get("enabled", False))
        kinds = [k for k, _ in MARKER_KINDS]
        items["MarkerKind"].CurrentIndex = kinds.index(interval.get("kind", "reel"))
        items["MarkerEvery"].Text = str(interval.get("every", "20m"))
        items["Reel"].Enabled = bool(p.get("ffoa_hour_per_reel"))
        items["Target"].Clear()
        items["Target"].AddItems([NO_TARGET] + list(p.get("target_durations", [])))
        items["Info"].Text = timeline_info()

    def collect():
        p = current_preset()
        slate = dict((key, items["S_" + key].Text) for key, _ in SLATE_INPUTS)
        target = items["Target"].CurrentText
        options = {
            "mode": MODES[max(items["Mode"].CurrentIndex, 0)][0],
            "reel": int(items["Reel"].Value) if p and p.get("ffoa_hour_per_reel") else 1,
            "include_head": bool(items["Head"].Checked),
            "include_tail": bool(items["Tail"].Checked),
            "markers_enabled": bool(items["Markers"].Checked),
            "marker_kind": MARKER_KINDS[max(items["MarkerKind"].CurrentIndex, 0)][0],
            "marker_every": items["MarkerEvery"].Text.strip() or None,
            "target_duration": None if target in ("", NO_TARGET) else target,
        }
        return p, slate, options

    def on_generate(ev):
        p, slate, options = collect()
        if not p:
            log("Seleziona un preset")
            return
        save_values({"preset": p["id"], "slate": slate, "options": options})
        log("—" * 20)
        try:
            plan = resolve_ops.generate(resolve, p, slate, options, log)
            log("Fatto." if not plan.warnings else "Fatto, con %d avvisi." % len(plan.warnings))
        except (resolve_ops.ResolveError, LayoutError, TimecodeError, presets.PresetError) as exc:
            log("ERRORE: %s" % exc)
        except Exception:
            log("ERRORE inatteso:\n" + traceback.format_exc())
        items["Info"].Text = timeline_info()

    def on_remove(ev):
        try:
            project = resolve.GetProjectManager().GetCurrentProject()
            tl = project.GetCurrentTimeline() if project else None
            if not tl:
                log("Nessuna timeline attiva")
                return
            resolve_ops.remove_leaderkit(tl, log)
        except Exception:
            log("ERRORE inatteso:\n" + traceback.format_exc())

    def on_close(ev):
        disp.ExitLoop()

    win.On.Preset.CurrentIndexChanged = on_preset
    win.On.Generate.Clicked = on_generate
    win.On.Remove.Clicked = on_remove
    win.On.Close.Clicked = on_close
    win.On.LeaderKitWin.Close = on_close

    # Ripristina gli ultimi valori.
    ids = [p["id"] for p in found]
    if values.get("preset") in ids:
        items["Preset"].CurrentIndex = ids.index(values["preset"])
    on_preset()
    for key, _ in SLATE_INPUTS:
        items["S_" + key].Text = values.get("slate", {}).get(key, "")
    if not items["S_date"].Text:
        items["S_date"].Text = datetime.date.today().isoformat()
    mode_ids = [m for m, _ in MODES]
    saved_mode = values.get("options", {}).get("mode")
    if saved_mode in mode_ids:
        items["Mode"].CurrentIndex = mode_ids.index(saved_mode)
    log("Preset: %s — dati utente: %s" % (paths.factory_presets_dir(), paths.user_presets_dir()))

    win.Show()
    disp.RunLoop()
    win.Hide()
