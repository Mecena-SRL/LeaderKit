#!/bin/bash
# LeaderKit — installazione per l'utente corrente (macOS e Linux).
# Copia lo script, la libreria, i preset e il bundle .drfx nella cartella
# Fusion di DaVinci Resolve. Non richiede privilegi di amministratore.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD="$HERE/payload"
case "$(uname -s)" in
  Darwin) FUSION="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion" ;;
  Linux)  FUSION="$HOME/.local/share/DaVinciResolve/Fusion" ;;
  *) echo "Sistema non supportato: $(uname -s)"; exit 1 ;;
esac

if [ "${1:-}" = "--uninstall" ]; then
  rm -f  "$FUSION/Scripts/Utility/LeaderKit.py"
  rm -f  "$FUSION/Templates/LeaderKit.drfx"
  rm -rf "$FUSION/LeaderKit/leaderkit" "$FUSION/LeaderKit/presets" "$FUSION/LeaderKit/VERSION"
  echo "LeaderKit rimosso. I preset utente restano in: $FUSION/LeaderKit/presets-user"
else
  mkdir -p "$FUSION/Scripts/Utility" "$FUSION/Templates" "$FUSION/LeaderKit/presets-user"
  rm -rf "$FUSION/LeaderKit/leaderkit" "$FUSION/LeaderKit/presets"
  cp -R "$PAYLOAD/LeaderKit/." "$FUSION/LeaderKit/"
  cp "$PAYLOAD/Scripts/Utility/LeaderKit.py" "$FUSION/Scripts/Utility/LeaderKit.py"
  cp "$HERE/LeaderKit.drfx" "$FUSION/Templates/LeaderKit.drfx"
  echo "LeaderKit $(cat "$FUSION/LeaderKit/VERSION") installato in:"
  echo "  $FUSION"
  if ! command -v python3 >/dev/null 2>&1 && [ ! -d "/Library/Frameworks/Python.framework" ]; then
    echo
    echo "ATTENZIONE: Python 3 non trovato. Gli script Python di Resolve richiedono"
    echo "Python 3 installato nel sistema (su macOS: installer di python.org)."
  fi
  echo
  echo "Riavvia DaVinci Resolve, poi: Workspace > Scripts > LeaderKit"
fi

if [ -t 0 ] && [ "${LEADERKIT_NO_PAUSE:-}" = "" ]; then
  read -r -p "Premi Invio per chiudere… " _ || true
fi
