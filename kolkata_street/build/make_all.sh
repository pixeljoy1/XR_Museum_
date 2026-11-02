#!/usr/bin/env bash
# Build the whole project from nothing.
#
#   ./build/make_all.sh                       # models, kit, street
#   ./build/make_all.sh --preview             # ... and render every preview sheet
#   BLENDER=/path/to/blender ./build/make_all.sh
#
# The two vehicles and the city kit are independent; the street links all three,
# so it has to come last.
set -euo pipefail
cd "$(dirname "$0")/.."

BLENDER="${BLENDER:-}"
if [ -z "$BLENDER" ]; then
  for c in \
    "/Applications/Blender.app/Contents/MacOS/Blender" \
    "$(command -v blender || true)" \
    "/opt/bl/blender-4.2.9-linux-x64/blender"; do
    if [ -n "$c" ] && [ -x "$c" ]; then BLENDER="$c"; break; fi
  done
fi
if [ -z "$BLENDER" ]; then
  echo "Blender not found. Set BLENDER=/path/to/blender" >&2; exit 1
fi
echo "using $BLENDER"
"$BLENDER" --version | head -1

# macOS still ships bash 3.2, where "${arr[@]}" on an EMPTY array trips `set -u`.
# ${arr[@]+"${arr[@]}"} expands to nothing when the array is empty and to the
# quoted elements when it is not.
EXTRA=("$@")
run () {
  echo; echo "=== $1 ==="
  "$BLENDER" -b -P "build/$1" -- ${EXTRA[@]+"${EXTRA[@]}"}
}

run build_tram.py
run build_ambassador.py
run build_city_kit.py
run build_street.py

echo
echo "done."
echo "  assets/tram_ctc.blend"
echo "  assets/ambassador_taxi.blend"
echo "  assets/city_kit.blend"
echo "  scene/kolkata_street.blend   <- open this"
echo
echo "list the cameras:"
echo "  $BLENDER -b scene/kolkata_street.blend -P build/render.py -- --list"
