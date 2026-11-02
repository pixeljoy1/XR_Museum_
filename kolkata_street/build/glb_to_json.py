#!/usr/bin/env python3
"""Convert .glb to self-contained .gltf JSON, written with a .json extension.

Some static hosts serve only a fixed set of file types, and .glb is often not
one of them. A glTF JSON with its buffer inlined as a base64 data URI is the
same model in a form any host will serve as plain JSON, and three.js's
GLTFLoader parses it without caring what the file is called. Base64 costs about
a third more bytes, which for untextured geometry is a few hundred kB.

    python3 build/glb_to_json.py <in-dir> <out-dir>
"""
import base64, json, os, struct, sys

JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942


def convert(path):
    raw = open(path, 'rb').read()
    magic, version, total = struct.unpack_from('<4sII', raw, 0)
    if magic != b'glTF':
        raise ValueError('%s is not a GLB' % path)
    doc, binary, off = None, None, 12
    while off < total:
        length, ctype = struct.unpack_from('<II', raw, off)
        data = raw[off + 8: off + 8 + length]
        if ctype == JSON_CHUNK:
            doc = json.loads(data.decode('utf-8'))
        elif ctype == BIN_CHUNK:
            binary = data
        off += 8 + length + ((4 - length % 4) % 4 if length % 4 else 0)
    if doc is None:
        raise ValueError('%s has no JSON chunk' % path)
    for buf in doc.get('buffers', []):
        if 'uri' in buf:
            continue                      # already external or inline
        n = buf['byteLength']             # the GLB chunk is padded; the buffer is not
        buf['uri'] = ('data:application/octet-stream;base64,'
                      + base64.b64encode(binary[:n]).decode('ascii'))
    return doc


def main():
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    total_in = total_out = 0
    for name in sorted(os.listdir(src)):
        if not name.endswith('.glb'):
            continue
        out = os.path.join(dst, name[:-4] + '.json')
        with open(out, 'w') as f:
            json.dump(convert(os.path.join(src, name)), f, separators=(',', ':'))
        a = os.path.getsize(os.path.join(src, name))
        b = os.path.getsize(out)
        total_in += a
        total_out += b
        print('  %-24s %6.0f kB -> %6.0f kB' % (name, a / 1024, b / 1024))
    print('%d files: %.1f MB -> %.1f MB' %
          (len(os.listdir(dst)), total_in / 1e6, total_out / 1e6))


main()
