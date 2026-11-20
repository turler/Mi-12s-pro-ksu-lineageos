#!/usr/bin/env python3
"""Gate: every symbol CRC referenced by every stock module (vendor_boot first-stage +
vendor_dlkm + system_dlkm + vendor) must match the new vmlinux.symvers.
Exit 1 on any mismatch or if fewer than 400 stock modules were found."""
import glob
import struct
import sys


def versions(path):
    d = open(path, 'rb').read()
    shoff = struct.unpack_from('<Q', d, 0x28)[0]
    se, sn, si = struct.unpack_from('<HHH', d, 0x3a)
    secs = [struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * se) for i in range(sn)]
    so = secs[si][4]

    def nm(o):
        return d[so + o:d.index(b'\0', so + o)].decode()

    for s in secs:
        if nm(s[0]) == '__versions':
            v = d[s[4]:s[4] + s[5]]
            return {v[i + 8:i + 64].split(b'\0')[0].decode(): struct.unpack_from('<Q', v, i)[0] & 0xffffffff
                    for i in range(0, len(v), 64)}
    return {}


sv = {l.split()[1]: int(l.split()[0], 16) for l in open(sys.argv[1])}
mods = sorted(glob.glob('stock/dlkm/**/*.ko', recursive=True)
              + glob.glob('stock/vbx/x_ramdisk.cpio/lib/modules/*.ko'))
bad, refs = {}, 0
for m in mods:
    for n, c in versions(m).items():
        if n == 'module_layout' or n not in sv:
            continue
        refs += 1
        if sv[n] != c:
            bad.setdefault(n, set()).add(m.split('/')[-1])
print(f"modules={len(mods)} refs_checked={refs} mismatched_symbols={len(bad)}")
for n, ms in sorted(bad.items()):
    print(" MISMATCH", n, hex(sv[n]), sorted(ms))
sys.exit(1 if bad or len(mods) < 400 else 0)
