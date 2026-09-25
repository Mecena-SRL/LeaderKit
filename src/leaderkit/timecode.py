"""Frame rate e timecode SMPTE, drop-frame incluso.

Tutto il plugin ragiona in fotogrammi interi della timeline. I "secondi" di un
leader sono sempre secondi *nominali* (24 fotogrammi a 23.976, 30 a 29.97):
è la convenzione dei leader e del timecode, per cui il 2-pop a -2" cade a
48 fotogrammi dal FFOA a 23.976 e a 60 fotogrammi a 29.97 DF.
"""

import re
from fractions import Fraction

# Frequenze che Resolve espone in timelineFrameRate -> valore esatto.
_EXACT_RATES = {
    "16": Fraction(16), "18": Fraction(18),
    "23.976": Fraction(24000, 1001), "24": Fraction(24), "25": Fraction(25),
    "29.97": Fraction(30000, 1001), "30": Fraction(30),
    "47.952": Fraction(48000, 1001), "48": Fraction(48), "50": Fraction(50),
    "59.94": Fraction(60000, 1001), "60": Fraction(60),
    "72": Fraction(72), "95.904": Fraction(96000, 1001), "96": Fraction(96),
    "100": Fraction(100), "119.88": Fraction(120000, 1001), "120": Fraction(120),
}

# Il drop-frame esiste solo per i multipli NTSC di 30.
_DROP_FRAMES_PER_MINUTE = {30: 2, 60: 4, 120: 8}


class TimecodeError(ValueError):
    pass


class FrameRate(object):
    """Frequenza di timeline: valore esatto, base nominale intera, drop-frame."""

    def __init__(self, exact, drop_frame=False):
        self.exact = Fraction(exact)
        self.nominal = int(round(float(self.exact)))
        is_ntsc = self.exact.denominator == 1001
        if drop_frame and not (is_ntsc and self.nominal in _DROP_FRAMES_PER_MINUTE):
            raise TimecodeError("Il drop-frame non esiste a %s fps" % self.label_number())
        self.drop_frame = bool(drop_frame)
        self.is_ntsc = is_ntsc

    @classmethod
    def parse(cls, value, drop_frame=None):
        """Interpreta il valore di Resolve ("25", "29.97", "29.97 DF", 23.976...).

        ``drop_frame`` (se non None) prevale sul suffisso DF e arriva di solito
        dal setting ``timelineDropFrameTimecode``.
        """
        text = str(value).strip().upper()
        suffix_df = bool(re.search(r"\bDF\b", text))
        suffix_ndf = bool(re.search(r"\bNDF\b", text))
        number = re.sub(r"[^0-9.]", "", text.replace("NDF", "").replace("DF", ""))
        if not number:
            raise TimecodeError("Frame rate non valido: %r" % (value,))
        key = number.rstrip("0").rstrip(".") if "." in number else number
        exact = _EXACT_RATES.get(key)
        if exact is None:
            # Accetta anche 23.98 / 29.97002997... arrotondando alla tabella.
            f = float(number)
            for k, v in _EXACT_RATES.items():
                if abs(float(v) - f) < 0.006:
                    exact = v
                    break
        if exact is None:
            raise TimecodeError("Frame rate non supportato: %r" % (value,))
        if drop_frame is None:
            drop_frame = suffix_df and not suffix_ndf
        return cls(exact, bool(drop_frame))

    @property
    def fps(self):
        return float(self.exact)

    @property
    def drop_per_minute(self):
        return _DROP_FRAMES_PER_MINUTE.get(self.nominal, 0) if self.drop_frame else 0

    def label_number(self):
        if self.exact.denominator == 1:
            return str(self.exact.numerator)
        return ("%.3f" % float(self.exact)).rstrip("0").rstrip(".")

    def label(self):
        """Etichetta da slate: "25 fps", "29.97 fps DF"."""
        text = "%s fps" % self.label_number()
        if self.drop_frame:
            text += " DF"
        elif self.nominal in _DROP_FRAMES_PER_MINUTE and self.is_ntsc:
            text += " NDF"
        return text

    def seconds_to_frames(self, seconds):
        """Secondi *nominali* di leader -> fotogrammi (sempre interi)."""
        frames = Fraction(seconds) * self.nominal
        if frames.denominator != 1:
            raise TimecodeError("%s s non è un numero intero di fotogrammi a %s"
                                % (seconds, self.label()))
        return int(frames)

    def real_seconds(self, frames):
        return float(Fraction(frames) / self.exact)

    def __eq__(self, other):
        return (isinstance(other, FrameRate) and self.exact == other.exact
                and self.drop_frame == other.drop_frame)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.exact, self.drop_frame))

    def __repr__(self):
        return "FrameRate(%s)" % self.label()


_TC_RE = re.compile(r"^\s*(-)?(\d{1,2})[:;.](\d{2})[:;.](\d{2})[:;.,](\d{2,3})\s*$")


def tc_to_frames(tc, rate):
    """"HH:MM:SS:FF" (o ;FF) -> numero di fotogrammi dall'origine 00:00:00:00."""
    m = _TC_RE.match(str(tc))
    if not m:
        raise TimecodeError("Timecode non valido: %r" % (tc,))
    neg = bool(m.group(1))
    h, mi, s, f = (int(m.group(i)) for i in range(2, 6))
    n = rate.nominal
    if mi > 59 or s > 59 or f >= n:
        raise TimecodeError("Timecode fuori range a %s: %r" % (rate.label(), tc))
    frames = ((h * 60 + mi) * 60 + s) * n + f
    drop = rate.drop_per_minute
    if drop:
        if s == 0 and f < drop and mi % 10 != 0:
            raise TimecodeError("%r non esiste in drop-frame (fotogramma saltato)" % (tc,))
        total_minutes = h * 60 + mi
        frames -= drop * (total_minutes - total_minutes // 10)
    return -frames if neg else frames


def frames_to_tc(frames, rate):
    """Numero di fotogrammi -> timecode; separatore ';' in drop-frame."""
    frames = int(frames)
    if frames < 0:
        return "-" + frames_to_tc(-frames, rate)
    n = rate.nominal
    drop = rate.drop_per_minute
    if drop:
        per_10_min = n * 600 - drop * 9
        per_min = n * 60 - drop
        d, m = divmod(frames, per_10_min)
        if m > drop:
            frames += drop * 9 * d + drop * ((m - drop) // per_min)
        else:
            frames += drop * 9 * d
    f = frames % n
    s = (frames // n) % 60
    mi = (frames // (n * 60)) % 60
    h = frames // (n * 3600)
    sep = ";" if drop else ":"
    return "%02d:%02d:%02d%s%02d" % (h, mi, s, sep, f)


_DUR_TOKEN = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*(h|m|min|s|f)?", re.I)


def duration_to_frames(expr, rate):
    """Durate/offset dei preset -> fotogrammi.

    Formati accettati: interi (fotogrammi), "8s", "-2s", "20m", "1h",
    "5s+12f", "-1s-1f", "12f", oppure un timecode ("00:00:08:00").
    I secondi sono nominali (vedi docstring del modulo).
    """
    if isinstance(expr, bool):
        raise TimecodeError("Durata non valida: %r" % (expr,))
    if isinstance(expr, int):
        return expr
    text = str(expr).strip().replace(" ", "")
    if not text:
        raise TimecodeError("Durata vuota")
    if _TC_RE.match(text):
        return tc_to_frames(text, rate)
    pos = 0
    total = Fraction(0)
    sign_carry = 1
    if text[0] in "+-":
        sign_carry = -1 if text[0] == "-" else 1
        text = text[1:]
    first = True
    while pos < len(text):
        m = _DUR_TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise TimecodeError("Durata non valida: %r" % (expr,))
        value = Fraction(m.group(1))
        if first:
            value *= sign_carry
            first = False
        unit = (m.group(2) or "f").lower()
        if unit == "f":
            if value.denominator != 1:
                raise TimecodeError("Fotogrammi non interi: %r" % (expr,))
            total += value
        elif unit == "s":
            total += value * rate.nominal
        elif unit in ("m", "min"):
            total += value * 60 * rate.nominal
        elif unit == "h":
            total += value * 3600 * rate.nominal
        pos = m.end()
    if total.denominator != 1:
        raise TimecodeError("%r non è un numero intero di fotogrammi a %s"
                            % (expr, rate.label()))
    return int(total)
