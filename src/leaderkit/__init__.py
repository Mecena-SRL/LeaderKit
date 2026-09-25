"""LeaderKit — leader, slate, countdown, sync pop e marker per DaVinci Resolve.

Il pacchetto è diviso in due parti:

* moduli puri (``timecode``, ``presets``, ``layout``, ``media``, ``fusion``),
  senza dipendenze da Resolve e coperti dai test;
* ``resolve_ops`` e ``ui``, che parlano con l'API di scripting di Resolve.
"""

__version__ = "0.4.0"
