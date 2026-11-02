#!/usr/bin/env bash
# Build the folder that gets deployed to the site.
#
#   ./build/make_web.sh                 -> dist/kolkataStreetXR/
#   ./build/make_web.sh --glb           -> same, but keep .glb (smaller; needs a
#                                          host that serves model/gltf-binary)
#
# The primary deployment is Aritra's portfolio:
#   https://pixeljoy1.github.io/aritra-portfolio/kolkataStreetXR/
# which serves .json assets, so that is the default here. Copy the whole folder
# into the portfolio repo at kolkataStreetXR/ and push.
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
[ -n "$BLENDER" ] || { echo "Blender not found. Set BLENDER=/path/to/blender" >&2; exit 1; }

USE_GLB=0
for a in "$@"; do [ "$a" = "--glb" ] && USE_GLB=1; done

OUT="dist/kolkataStreetXR"
rm -rf "$OUT"
mkdir -p "$OUT/models"

echo "=== flattening the scene (append, so nothing is a library link) ==="
"$BLENDER" -b -P build/build_street.py -- --append --out scene/_flat.blend

echo "=== exporting models and layout ==="
"$BLENDER" -b scene/_flat.blend -P build/export_web.py

cp ../docs/kolkata/index.html       "$OUT/index.html"
cp ../docs/kolkata/street.js        "$OUT/street.js"
cp ../docs/kolkata/xr-locomotion.js "$OUT/xr-locomotion.js"

if [ "$USE_GLB" = "1" ]; then
  cp ../docs/kolkata/models/*.glb "$OUT/models/"
  cp ../docs/kolkata/layout.json  "$OUT/layout.json"
  echo "=== .glb assets (host must serve model/gltf-binary) ==="
else
  python3 build/glb_to_json.py ../docs/kolkata/models "$OUT/models" >/dev/null
  python3 - "$OUT/layout.json" <<'PY'
import json, sys
src = '../docs/kolkata/layout.json'
d = json.load(open(src))
d['asset_ext'] = '.json'          # self-contained glTF, served as plain JSON
json.dump(d, open(sys.argv[1], 'w'), indent=1)
PY
  echo "=== .json assets (served anywhere) ==="
fi

echo
du -sh "$OUT"
find "$OUT" -type f | wc -l | xargs echo "files:"
echo
echo "deploy:"
echo "  cp -R $OUT <aritra-portfolio>/kolkataStreetXR"
echo "  cd <aritra-portfolio> && git add -A && git commit -m 'Kolkata street XR' && git push"
