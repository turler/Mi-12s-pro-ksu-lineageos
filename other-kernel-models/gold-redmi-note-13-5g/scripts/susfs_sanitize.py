#!/usr/bin/env python3
"""susfs_sanitize.py <in.patch> <out.patch>
Drops the legacy manual-KernelSU hook parts from the susfs4ksu 50_add_susfs_in_gki-android15-6.6 patch
(KernelSU-Next v3.4.2 hooks via its own syscall/LSM hooks) and keeps only the SUSFS VFS hooks."""
import re, sys
src = open(sys.argv[1], encoding='utf-8', errors='replace').read()
DROP_FILES = {'drivers/input/input.c', 'fs/exec.c', 'fs/read_write.c', 'kernel/reboot.c',
              'security/selinux/hooks.c', 'security/selinux/selinuxfs.c'}
MARK = {'fs/open.c': ('ksu_handle_faccessat', 'ksu_su_compat_enabled', 'struct filename *fname = NULL'),
        'fs/stat.c': ('ksu_handle_stat', 'ksu_handle_vfs_fstat', 'ksu_is_init_rc_hook_enabled',
                      'ksu_su_compat_enabled', 'struct filename *fname = NULL'),
        'kernel/sys.c': ('ksu_handle_setresuid',)}
out = []
for chunk in re.split(r'(?=^diff --git )', src, flags=re.M):
    if not chunk.startswith('diff --git '):
        out.append(chunk); continue
    path = re.match(r'diff --git a/(\S+) b/', chunk).group(1)
    if path in DROP_FILES:
        print('[drop file]', path); continue
    if path in MARK:
        parts = re.split(r'(?=^@@ )', chunk, flags=re.M)
        kept = []
        for h in parts[1:]:
            if any(m in h for m in MARK[path]):
                print('[drop hunk]', path, h.split('\n')[0][:60]); continue
            kept.append(h)
        if not kept: continue
        chunk = parts[0] + ''.join(kept)
    out.append(chunk)
final = ''.join(out)
for bad in ('ksu_handle_setresuid', 'ksu_handle_faccessat', 'ksu_handle_execveat_sucompat',
            'ksu_is_init_rc_hook_enabled'):
    assert bad not in final, bad
open(sys.argv[2], 'w').write(final)
