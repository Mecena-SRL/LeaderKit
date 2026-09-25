"""Calcolo del layout: dal preset + parametri reali della timeline a una lista
di elementi posizionati al fotogramma.

Asse dei tempi: fotogrammi assoluti dall'origine 00:00:00:00 alla frequenza
della timeline (``timecode.tc_to_frames``). Gli offset di testa sono relativi
al FFOA (primo fotogramma di programma), quelli di coda al LFOA (ultimo
fotogramma di programma): "+2s" in coda = LFOA + 2 secondi nominali, il
simmetrico esatto del 2-pop a "-2s" dal FFOA.
"""

from . import presets as presets_mod
from .timecode import duration_to_frames, frames_to_tc, tc_to_frames

CUSTOM_DATA_PREFIX = "leaderkit"

SLATE_LABELS = {
    "title": "TITLE", "director": "DIRECTOR", "editor": "EDITOR",
    "colorist": "COLORIST", "date": "DATE", "version": "VERSION",
    "duration": "DURATION", "fps": "FRAME RATE", "resolution": "RESOLUTION",
}


class LayoutError(ValueError):
    pass


class Element(object):
    """Un blocco video sulla traccia LeaderKit."""

    def __init__(self, kind, start, duration, **params):
        self.kind = kind          # slate | countdown | picture_start | pop | card | black
        self.start = start        # fotogramma assoluto
        self.duration = duration  # fotogrammi
        self.params = params

    @property
    def end(self):
        """Fotogramma successivo all'ultimo (esclusivo)."""
        return self.start + self.duration

    def __repr__(self):
        return "Element(%s, %d, %d, %r)" % (self.kind, self.start, self.duration, self.params)


class AudioEvent(object):
    def __init__(self, kind, start, duration, tone_hz, level_dbfs):
        self.kind = kind
        self.start = start
        self.duration = duration
        self.tone_hz = tone_hz
        self.level_dbfs = level_dbfs

    def __repr__(self):
        return "AudioEvent(%s, %d, %d)" % (self.kind, self.start, self.duration)


class Marker(object):
    def __init__(self, frame, color, name, note, custom_data, duration=1):
        self.frame = frame        # fotogramma assoluto
        self.color = color
        self.name = name
        self.note = note
        self.custom_data = custom_data
        self.duration = duration

    def __repr__(self):
        return "Marker(%d, %s, %r)" % (self.frame, self.color, self.name)


class Plan(object):
    """Risultato del layout, indipendente da Resolve."""

    def __init__(self, preset, rate, width, height):
        self.preset = preset
        self.rate = rate
        self.width = width
        self.height = height
        self.ffoa = None
        self.lfoa = None
        self.elements = []
        self.audio = []
        self.markers = []
        self.warnings = []
        self.slate_lines = []
        self.slate_values = {}

    @property
    def start(self):
        firsts = [e.start for e in self.elements] + [self.ffoa]
        return min(firsts)

    @property
    def end(self):
        """Fotogramma esclusivo di fine timeline."""
        lasts = [e.end for e in self.elements] + [self.lfoa + 1]
        return max(lasts)

    @property
    def program_duration(self):
        return self.lfoa - self.ffoa + 1

    def tc(self, frame):
        return frames_to_tc(frame, self.rate)

    def head_elements(self):
        return [e for e in self.elements if e.start < self.ffoa]

    def tail_elements(self):
        return [e for e in self.elements if e.start > self.lfoa]

    def summary(self):
        lines = ["Preset: %s" % self.preset["name"],
                 "Timeline: %s, %dx%d" % (self.rate.label(), self.width, self.height),
                 "Inizio leader: %s" % self.tc(self.start),
                 "FFOA: %s  LFOA: %s  durata programma: %s (%d fotogrammi)" % (
                     self.tc(self.ffoa), self.tc(self.lfoa),
                     frames_to_tc(self.program_duration, self.rate), self.program_duration),
                 "Fine timeline: %s" % self.tc(self.end - 1)]
        for a in self.audio:
            lines.append("%s: %s (%d fotogrammi, %g Hz, %g dBFS)" % (
                a.kind, self.tc(a.start), a.duration, a.tone_hz, a.level_dbfs))
        for w in self.warnings:
            lines.append("ATTENZIONE: " + w)
        return "\n".join(lines)


def custom_data(kind):
    return "%s:%s" % (CUSTOM_DATA_PREFIX, kind)


def _frames(expr, rate, where):
    try:
        return duration_to_frames(expr, rate)
    except ValueError as exc:
        raise LayoutError("%s: %s" % (where, exc))


def ffoa_frame(preset, rate, reel=1):
    """FFOA del preset; con ``ffoa_hour_per_reel`` l'ora diventa il numero di rullo."""
    tc = preset["ffoa_tc"]
    if preset.get("ffoa_hour_per_reel") and reel != 1:
        if not 1 <= int(reel) <= 23:
            raise LayoutError("Numero di rullo fuori range: %r" % (reel,))
        tc = "%02d%s" % (int(reel), tc[2:])
    return tc_to_frames(tc, rate)


def _pop_elements(ev, anchor, rate, where):
    at = anchor + _frames(ev["at"], rate, where)
    frames = int(ev.get("frames", 1))
    if frames < 1:
        raise LayoutError("%s: frames deve essere >= 1" % where)
    video = ev.get("video", "two")
    els = [Element("pop", at, frames, style=video)]
    auds = []
    if ev.get("tone_hz", 1000):
        auds.append(AudioEvent("pop", at, frames, float(ev.get("tone_hz", 1000)),
                               float(ev.get("level_dbfs", -20))))
    return els, auds


def _section(events, anchor, rate, section):
    elements, audio = [], []
    for i, ev in enumerate(events):
        where = "%s[%d] (%s)" % (section, i, ev["type"])
        t = ev["type"]
        if t == "countdown":
            first, last = ev["from"], ev["to"]
            ps = int(ev.get("picture_start_frames", 0))
            sweep = bool(ev.get("sweep", True))
            one = rate.nominal
            for digit in range(first, last - 1, -1):
                start = anchor - digit * one
                dur = one
                if digit == first and ps:
                    if ps >= one:
                        raise LayoutError("%s: picture_start_frames troppo lungo" % where)
                    elements.append(Element("picture_start", start, ps))
                    start += ps
                    dur -= ps
                elements.append(Element("countdown", start, dur, digit=digit, sweep=sweep,
                                        phase=one - dur))
        elif t == "pop":
            els, auds = _pop_elements(ev, anchor, rate, where)
            elements += els
            audio += auds
        else:
            start = anchor + _frames(ev["start"], rate, where)
            dur = _frames(ev["duration"], rate, where)
            if dur < 1:
                raise LayoutError("%s: durata nulla" % where)
            params = {}
            if t == "card":
                params["text"] = ev.get("text", "END OF PROGRAM")
            elements.append(Element(t, start, dur, **params))
    return elements, audio


def _check_overlaps(elements):
    ordered = sorted(elements, key=lambda e: e.start)
    for a, b in zip(ordered, ordered[1:]):
        if b.start < a.end:
            raise LayoutError("Elementi sovrapposti: %s e %s" % (a.kind, b.kind))
    return ordered


def _fill_black(elements, start, end):
    """Riempie di nero i buchi tra start ed end (esclusivo)."""
    out = []
    cursor = start
    for e in elements:
        if e.start > cursor:
            out.append(Element("black", cursor, e.start - cursor))
        out.append(e)
        cursor = max(cursor, e.end)
    if end > cursor:
        out.append(Element("black", cursor, end - cursor))
    return out


def build_plan(preset, rate, width, height, program_duration, slate_values=None,
               options=None):
    """Costruisce il Plan.

    ``program_duration``: fotogrammi di programma (FFOA..LFOA inclusi).
    ``slate_values``: dict dei campi slate compilati a mano.
    ``options``: reel (int), include_head/include_tail (bool), markers_enabled
    (bool), marker_kind ("reel"/"break"), marker_every (str/int),
    target_duration (str/int o None).
    """
    options = options or {}
    slate_values = dict(slate_values or {})
    if program_duration < 1:
        raise LayoutError("Il programma è vuoto: servono almeno 1 fotogramma")
    if width < 1 or height < 1:
        raise LayoutError("Risoluzione timeline non valida: %sx%s" % (width, height))

    plan = Plan(preset, rate, int(width), int(height))
    plan.ffoa = ffoa_frame(preset, rate, options.get("reel", 1))
    plan.lfoa = plan.ffoa + int(program_duration) - 1

    head, head_audio = [], []
    if options.get("include_head", True):
        head, head_audio = _section(preset.get("head", []), plan.ffoa, rate, "head")
        for e in head:
            if e.end > plan.ffoa:
                raise LayoutError("head: '%s' finisce oltre il FFOA" % e.kind)
    tail, tail_audio = [], []
    tail_len = 0
    if options.get("include_tail", True):
        tail_len = _frames(preset.get("tail_duration", 0), rate, "tail_duration")
        tail, tail_audio = _section(preset.get("tail", []), plan.lfoa, rate, "tail")
        for e in tail:
            if e.start <= plan.lfoa or e.end > plan.lfoa + tail_len + 1:
                raise LayoutError("tail: '%s' esce dall'intervallo della coda "
                                  "(LFOA+1 .. LFOA+tail_duration)" % e.kind)

    head = _check_overlaps(head)
    tail = _check_overlaps(tail)
    if head:
        head = _fill_black(head, head[0].start, plan.ffoa)
    if tail_len:
        tail = _fill_black(tail, plan.lfoa + 1, plan.lfoa + 1 + tail_len)
    plan.elements = head + tail
    plan.audio = sorted(head_audio + tail_audio, key=lambda a: a.start)
    if plan.start < 0:
        raise LayoutError("Il leader inizierebbe prima di 00:00:00:00")

    _checks(plan, options)
    _slate(plan, slate_values)
    _markers(plan, options)
    return plan


def _checks(plan, options):
    preset, rate = plan.preset, plan.rate
    checks = preset.get("checks", {})
    if rate.is_ntsc and checks.get("warn_drop_frame"):
        plan.warnings.append(checks["warn_drop_frame"])
    expected = checks.get("expected_rates")
    if expected and rate.label_number() not in expected:
        hint = checks.get("rate_hint", "")
        plan.warnings.append(("Frequenza %s non prevista dal preset (attese: %s). %s"
                              % (rate.label(), ", ".join(expected), hint)).strip())
    resolutions = checks.get("expected_resolutions")
    if resolutions and [plan.width, plan.height] not in [list(r) for r in resolutions]:
        plan.warnings.append("Risoluzione %dx%d non prevista dal preset (attese: %s)." % (
            plan.width, plan.height, ", ".join("%dx%d" % tuple(r) for r in resolutions)))
    target = options.get("target_duration")
    plan.duration_delta = None
    if target:
        target_frames = _frames(target, rate, "target_duration")
        plan.duration_delta = plan.program_duration - target_frames
        if plan.duration_delta:
            msg = "Durata programma %s: %+d fotogrammi rispetto al target %s" % (
                frames_to_tc(plan.program_duration, rate), plan.duration_delta,
                frames_to_tc(target_frames, rate))
            if checks.get("strict_duration"):
                msg += " — il preset richiede durata esatta"
            plan.warnings.append(msg)


def _slate(plan, values):
    rate = plan.rate
    pops = [a for a in plan.audio if a.start < plan.ffoa]
    auto = {
        "duration": frames_to_tc(plan.program_duration, rate),
        "fps": rate.label(),
        "resolution": "%d × %d" % (plan.width, plan.height),
    }
    tokens = {
        "ffoa_tc": plan.tc(plan.ffoa), "lfoa_tc": plan.tc(plan.lfoa),
        "pop_tc": plan.tc(pops[0].start) if pops else "—",
        "start_tc": plan.tc(plan.start), "preset": plan.preset["name"],
    }
    merged = dict(values)
    merged.update(auto)
    plan.slate_values = merged
    slate_cfg = plan.preset.get("slate", {})
    lines = []
    for field in slate_cfg.get("fields", presets_mod.SLATE_FIELDS):
        if field == "title":
            continue  # il titolo ha il suo campo grafico
        value = (merged.get(field) or "").strip() or "—"
        lines.append("%s   %s" % (SLATE_LABELS[field], value))
    for extra in slate_cfg.get("extra_lines", []):
        try:
            lines.append(extra.format(**tokens))
        except (KeyError, IndexError, ValueError):
            lines.append(extra)
    plan.slate_lines = lines
    plan.slate_title = (merged.get("title") or "").strip() or "UNTITLED"
    plan.slate_heading = slate_cfg.get("heading", plan.preset["name"]).strip()


def _markers(plan, options):
    cfg = plan.preset.get("markers", {})
    rate = plan.rate
    out = []
    fl = cfg.get("ffoa_lfoa", {})
    if fl.get("enabled", True):
        color = fl.get("color", "Blue")
        out.append(Marker(plan.ffoa, color, "FFOA", "First frame of action " + plan.tc(plan.ffoa),
                          custom_data("ffoa")))
        out.append(Marker(plan.lfoa, color, "LFOA", "Last frame of action " + plan.tc(plan.lfoa),
                          custom_data("lfoa")))
    sync = cfg.get("sync", {})
    if sync.get("enabled", False):
        for a in plan.audio:
            head = a.start < plan.ffoa
            out.append(Marker(a.start, sync.get("color", "Cyan"),
                              "2-POP" if head else "TAIL POP",
                              "%s %s — %g Hz %g dBFS" % ("2-pop" if head else "Tail pop",
                                                        plan.tc(a.start), a.tone_hz, a.level_dbfs),
                              custom_data("pop" if head else "tailpop")))
    interval = cfg.get("interval", {})
    enabled = options.get("markers_enabled", interval.get("enabled", False))
    if enabled and interval:
        kind = options.get("marker_kind") or interval.get("kind", "reel")
        every = _frames(options.get("marker_every") or interval.get("every", "20m"),
                        rate, "markers.interval.every")
        if every < 1:
            raise LayoutError("Intervallo marker nullo")
        color = options.get("marker_color") or interval.get(
            "color", "Red" if kind == "reel" else "Yellow")
        n = 1
        frame = plan.ffoa + every
        while frame < plan.lfoa:
            if kind == "reel":
                name = "Fine rullo %d" % n
                note = "Cambio rullo %d → %d a %s (%s dal FFOA)" % (
                    n, n + 1, plan.tc(frame), frames_to_tc(frame - plan.ffoa, rate))
            else:
                name = "Break %d" % n
                note = "Break %d a %s (%s dal FFOA)" % (
                    n, plan.tc(frame), frames_to_tc(frame - plan.ffoa, rate))
            out.append(Marker(frame, color, name, note, custom_data("%s:%d" % (kind, n))))
            n += 1
            frame += every
    seen = set()
    unique = []
    for m in out:  # Resolve accetta un solo marker per fotogramma
        if m.frame in seen:
            plan.warnings.append("Marker '%s' scartato: fotogramma %s già occupato"
                                 % (m.name, plan.tc(m.frame)))
            continue
        seen.add(m.frame)
        unique.append(m)
    plan.markers = sorted(unique, key=lambda m: m.frame)
