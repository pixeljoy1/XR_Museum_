#!/usr/bin/env bash
# Build the folder that gets deployed to the site.
#
#   ./build/make_web.sh                 -> dist/kolkataStreetXR/
#   ./build/make_web.sh --glb           -> same, but keep .glb (smaller; needs a
#                                          host that serves model/gltf-binary)
#   ./build/make_web.sh --back ../experiences/kolkata-street-vr/
#                                       -> show a link back to the host page
#   ./build/make_web.sh --cdn           -> load A-Frame from a CDN instead of
#                                          vendoring it (default is to vendor)
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
VENDOR=1
BACK=""
prev=""
for a in "$@"; do
  [ "$a" = "--glb" ] && USE_GLB=1
  [ "$a" = "--cdn" ] && VENDOR=0
  [ "$prev" = "--back" ] && BACK="$a"
  prev="$a"
done
AFRAME_VER=1.7.0
AFRAME_CDN="https://cdn.jsdelivr.net/npm/aframe@${AFRAME_VER}/dist/aframe.min.js"

OUT="dist/kolkataStreetXR"
rm -rf "$OUT"
mkdir -p "$OUT/models"

echo "=== flattening the scene (append, so nothing is a library link) ==="
"$BLENDER" -b -P build/build_street.py -- --append --out scene/_flat.blend

echo "=== exporting models and layout ==="
"$BLENDER" -b scene/_flat.blend -P build/export_web.py

cp ../docs/kolkata/index.html       "$OUT/index.html"
# The host page can wrap this one. --back <href> turns on the link back to it;
# the page itself reads data-back off the scene, so the host never has to keep
# a patched copy of index.html that the next deploy would overwrite.
# A third-party script is one more thing that can be down when someone picks up
# the headset. The spec's own rule is to avoid third-party requests and
# self-host (it says it of fonts; the same argument applies here), so by default
# A-Frame is vendored next to the page and the tag is rewritten to point at it.
if [ "$VENDOR" = "1" ]; then
  mkdir -p "$OUT/vendor"
  if curl -fsS -o "$OUT/vendor/aframe-${AFRAME_VER}.min.js" "$AFRAME_CDN"; then
    python3 - "$OUT/index.html" "$AFRAME_CDN" "vendor/aframe-${AFRAME_VER}.min.js" <<'PY'
import sys
p, cdn, local = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(p).read()
assert cdn in s, 'A-Frame script tag not found: ' + cdn
open(p, 'w').write(s.replace(cdn, local))
PY
    echo "A-Frame vendored -> vendor/aframe-${AFRAME_VER}.min.js ($(du -h "$OUT/vendor/aframe-${AFRAME_VER}.min.js" | cut -f1))"
  else
    echo "WARNING: could not fetch A-Frame; the page will load it from the CDN" >&2
    rmdir "$OUT/vendor" 2>/dev/null || true
  fi
fi

if [ -n "$BACK" ]; then
  python3 - "$OUT/index.html" "$BACK" <<'PY'
import sys
p, back = sys.argv[1], sys.argv[2]
s = open(p).read()
old = '      xr-locomotion='
assert old in s, 'scene tag not found'
s = s.replace(old, '      data-back="%s"\n' % back + old, 1)
open(p, 'w').write(s)
PY
  echo "back link -> $BACK"
fi
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
