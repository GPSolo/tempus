#!/usr/bin/env bash
# Seeds the saved server/login into a Tempo debug build after install, so a fresh
# install doesn't require typing the server and credentials on the phone again.
#
# Reads debug-server.properties in the repo root (see debug-server.properties.example):
#   server=    https://subsonic.example.com:4533
#   user=      youruser
#   password=  yourpassword
#   server_id= (optional; stable id used for cache keys, random UUID if omitted)
#
# Usage: scripts/seed-debug-login.sh <tempus|degoogled|play>
set -euo pipefail

FLAVOR="${1:-degoogled}"
PROPS="$(cd "$(dirname "$0")/.." && pwd)/debug-server.properties"

case "$FLAVOR" in
    tempus)    PKG="com.eddyizm.tempus.debug" ;;
    degoogled) PKG="com.eddyizm.degoogled.tempus.debug" ;;
    play)      PKG="com.eddyizm.play.tempus.debug" ;;
    *) echo "usage: $0 <tempus|degoogled|play>" >&2; exit 2 ;;
esac

if ! adb get-state >/dev/null 2>&1; then
    echo "No device connected — skipping login seed." >&2
    exit 0
fi

if [ ! -f "$PROPS" ]; then
    echo "No $PROPS found — skipping login seed." >&2
    exit 0
fi

get() { sed -n "s/^$1=//p" "$PROPS" | head -n1; }
SERVER="$(get server)"
USER="$(get user)"
PASS="$(get password)"
SERVER_ID="$(get server_id)"

if [ -z "$SERVER" ] || [ -z "$USER" ] || [ -z "$PASS" ]; then
    echo "$PROPS must define server, user and password." >&2
    exit 1
fi
if [ -z "$SERVER_ID" ]; then
    SERVER_ID="$(command -v uuidgen >/dev/null 2>&1 && uuidgen || cat /proc/sys/kernel/random/uuid)"
fi

# Escape XML special characters so arbitrary credentials stay valid XML.
xml_escape() { sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g'; }

PREFS_FILE="/data/local/tmp/tempo_debug_prefs.xml"
TMP_XML="$(mktemp)"
trap 'rm -f "$TMP_XML"' EXIT

{
    echo "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>"
    echo "<map>"
    echo "    <string name=\"server\">$(printf '%s' "$SERVER" | xml_escape)</string>"
    echo "    <string name=\"server_id\">$(printf '%s' "$SERVER_ID" | xml_escape)</string>"
    echo "    <string name=\"user\">$(printf '%s' "$USER" | xml_escape)</string>"
    echo "    <string name=\"password\">$(printf '%s' "$PASS" | xml_escape)</string>"
    echo "    <boolean name=\"low_security\" value=\"false\" />"
    echo "</map>"
} > "$TMP_XML"

adb shell am force-stop "$PKG" 2>/dev/null || true
adb push "$TMP_XML" "$PREFS_FILE" >/dev/null
adb shell "run-as $PKG sh -c 'mkdir -p shared_prefs && cp $PREFS_FILE shared_prefs/${PKG}_preferences.xml && chmod 600 shared_prefs/${PKG}_preferences.xml'"
echo "Seeded login for $PKG"
