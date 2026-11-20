#!/usr/bin/env python3
"""modcrc.py <module.ko> [vmlinux.symvers|Module.symvers]
Dumps __versions of a .ko (like modprobe --dump-modversions) and, if a symvers
file is given, compares every imported symbol CRC. Exit 1 on any mismatch/missing."""
import subprocess, struct, sys, tempfile, os
ko = sys.argv[1]
with tempfile.TemporaryDirectory() as d:
    f = os.path.join(d, 'v')
    subprocess.run(['llvm-objcopy', '--dump-section', '__versions=' + f, ko, os.path.join(d, 'x.ko')], check=True)
    b = open(f, 'rb').read()
ents = []
for i in range(0, len(b), 64):
    crc = struct.unpack_from('<Q', b, i)[0] & 0xffffffff
    ents.append((crc, b[i + 8:i + 64].split(b'\0')[0].decode()))
if len(sys.argv) < 3:
    for c, n in ents: print('0x%08x\t%s' % (c, n))
    sys.exit(0)
sv = {}
for l in open(sys.argv[2]):
    p = l.split('\t')
    if len(p) >= 2: sv[p[1]] = int(p[0], 16)
bad = 0; ext = 0
for c, n in ents:
    if n == 'module_layout': pass
    s = sv.get(n)
    st = 'OK' if s == c else ('MISSING' if s is None else 'MISMATCH(built=0x%08x)' % s)
    if st == 'MISSING': ext += 1; st = 'EXTERNAL(not exported by vmlinux; vendor module dep)'
    elif st != 'OK': bad += 1
    print('0x%08x\t%-45s %s' % (c, n, st))
print('TOTAL=%d VMLINUX_MATCH=%d MISMATCH=%d EXTERNAL=%d' % (len(ents), len(ents)-bad-ext, bad, ext))
sys.exit(1 if bad else 0)
