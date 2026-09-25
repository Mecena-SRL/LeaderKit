"""Media di supporto generati localmente, solo con la libreria standard.

* Sequenza PNG nera alla risoluzione della timeline: è il "supporto" su cui
  si appoggiano gli elementi del leader. Serve perché l'API di Resolve
  posiziona al fotogramma solo clip del Media Pool (AppendToTimeline); sopra
  ogni clip viene poi importata la composizione Fusion che disegna la grafica.
  I file sono hard link dello stesso PNG, quindi occupano lo spazio di uno.
* WAV del tono di sync: il tono dura più di un fotogramma e il clip viene
  rifilato a N fotogrammi esatti sulla timeline, così lo stesso file va bene
  per qualunque frame rate.
"""

import math
import os
import shutil
import struct
import wave
import zlib

SEQUENCE_PREFIX = "LeaderKit_black_"
POP_PREFIX = "LeaderKit_pop_"


def _png_chunk(kind, data):
    chunk = kind + data
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)


def black_png_bytes(width, height):
    """PNG RGB 8 bit completamente nero, compresso riga per riga."""
    comp = zlib.compressobj(9)
    row = b"\x00" * (1 + width * 3)  # filtro 0 + pixel neri
    parts = []
    for _ in range(height):
        parts.append(comp.compress(row))
    parts.append(comp.flush())
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", b"".join(parts)) + _png_chunk(b"IEND", b""))


def sequence_dir_name(width, height, count):
    return "black_%dx%d_%d" % (width, height, count)


def ensure_black_sequence(cache_dir, width, height, count):
    """Crea (se manca) una sequenza di ``count`` PNG neri.

    Restituisce (cartella, lista dei percorsi in ordine).
    """
    folder = os.path.join(cache_dir, sequence_dir_name(width, height, count))
    names = ["%s%dx%d_%05d.png" % (SEQUENCE_PREFIX, width, height, i) for i in range(count)]
    paths = [os.path.join(folder, n) for n in names]
    if all(os.path.exists(p) for p in paths):
        return folder, paths
    tmp = folder + ".tmp"
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    first = os.path.join(tmp, names[0])
    with open(first, "wb") as fh:
        fh.write(black_png_bytes(width, height))
    for name in names[1:]:
        target = os.path.join(tmp, name)
        try:
            os.link(first, target)
        except (OSError, AttributeError):
            shutil.copyfile(first, target)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.rename(tmp, folder)
    return folder, paths


def pop_wav_name(tone_hz, level_dbfs):
    return "%s%dHz_%sdBFS.wav" % (POP_PREFIX, int(round(tone_hz)),
                                  ("%g" % level_dbfs).replace("-", "m").replace(".", "p"))


def write_tone_wav(path, tone_hz=1000.0, level_dbfs=-20.0, tone_seconds=0.25,
                   total_seconds=1.0, sample_rate=48000):
    """WAV mono 24 bit: sinusoide in testa, poi silenzio.

    Il clip viene rifilato sulla timeline a N fotogrammi esatti; 0,25 s di tono
    coprono fino a 4 fotogrammi anche a 16 fps.
    """
    amplitude = (10.0 ** (level_dbfs / 20.0)) * 8388607
    tone_n = int(round(tone_seconds * sample_rate))
    total_n = max(tone_n, int(round(total_seconds * sample_rate)))
    frames = bytearray()
    for i in range(total_n):
        v = int(round(amplitude * math.sin(2 * math.pi * tone_hz * i / sample_rate))) if i < tone_n else 0
        frames += struct.pack("<i", v)[:3]
    tmp = path + ".tmp"
    w = wave.open(tmp, "wb")
    try:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(sample_rate)
        w.writeframes(bytes(frames))
    finally:
        w.close()
    os.replace(tmp, path) if hasattr(os, "replace") else os.rename(tmp, path)
    return path


def ensure_pop_wav(cache_dir, tone_hz, level_dbfs):
    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir)
    path = os.path.join(cache_dir, pop_wav_name(tone_hz, level_dbfs))
    if not os.path.exists(path):
        write_tone_wav(path, tone_hz, level_dbfs)
    return path
