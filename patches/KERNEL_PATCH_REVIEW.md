# Adversarial review: `0002-susfs-wildcard-cusrom-untrusted-app.patch`

- Tree: `/home/minhdc/kbuild/kernel` (uncommitted diff == `patches/0002-...patch`, verified byte-identical)
- Plus the uncommitted KernelSU change: `ksun-work/kernel/hook/setuid_hook.c` (reached through the `drivers/kernelsu` symlink)
- Target: android12-5.10 GKI, arm64, `CONFIG_LTO_CLANG_FULL=y`, `KSU_SUSFS_SUS_PATH=y`, `KSU_SUSFS_SUS_MAP=y`
- Build check (objects only, no vmlinux link):
  `make O=out-ksu ... fs/namei.o fs/readdir.o fs/susfs.o fs/proc/base.o fs/proc/task_mmu.o security/selinux/hooks.o drivers/kernelsu/`
  → **EXIT 0, no warnings.**

## Verdict: **FAIL / CHANGES REQUESTED**

The design holds up: the flags are set in the right place, there are no refcount or RCU `dput` bugs, and the fake-qstr ENOENT path ends correctly. The problem is the hiding condition. It looks only at the name and the owner uid, which is too broad. It breaks real third-party apps, and it gives apps a way to detect the hiding. Two memory-safety races also need fixing. One small change fixes most of this: only hide on **read-only superblocks** (`sb_rdonly()`). See "Recommended fix" at the end.

| # | Severity | Finding |
|---|----------|---------|
| B1 | **High** | Any app whose package name contains "lineage" (for example NCSoft *Lineage M / 2M / W*: `com.ncsoft.lineage*`) cannot open its own APK, because `/data/app/~~X/<pkg>-Y` is owned by `system` (uid 1000 < 10000). The app crashes at launch. |
| B2 | **Med-High** | readdir hides matching names on **every** filesystem with no owner check, but lookup only hides when the owner uid is < 10000. The two disagree, so an app can detect the hiding. It also breaks user and app files (`/sdcard/Download/lineage-*.zip`, an app's own cache files: recursive delete fails with `ENOTEMPTY`). |
| B3 | **Medium** | Memory-safety races in `susfs_is_dentry_sus_path()`: `d_inode` is read twice during RCU-walk, so a concurrent unlink can cause a NULL dereference. `d_name` is read with no lock or RCU protection in some paths, so a rename can cause a torn read or a use-after-free. |
| B4 | Low-Med | A skipped dirent leaves `buf->error = -EINVAL`. If one `getdents` call sees only hidden entries before EOF, it returns `-EINVAL` instead of 0. An app can detect this by probing with a small buffer. |
| L1–L9 | Low / Info | Coverage gaps, scope creep, style. See below. |

---

## Checklist item 1: TIF bit safety: **PASS**

- `arch/arm64/include/asm/thread_info.h` uses TIF bits 0–26. KernelSU uses bit 63 (`policy/app_profile.h:7 TIF_KSU_DISABLE_ESCAPE_WITH_ROOT`). SuSFS uses bits 33–35. Bit 36 is free.
- `thread_info.flags` is `unsigned long` (64-bit), and all set/clear/test calls go through `set_bit()`/`test_bit()` on a long, so bit 36 is valid. The `_TIF_*` masks use `1 << n` int shifts, but bit 36 never goes into any mask (`_TIF_WORK_MASK`, `_TIF_SYSCALL_WORK`), so entry code never reads it.

## Checklist item 2: propagation and locking: **PASS, with notes**

- `for_each_thread(current, t)` under `rcu_read_lock()` is correct: it traverses `signal->thread_head` with RCU, `set_ti_thread_flag()` is an atomic bitop, and nothing in the loop sleeps.
- **Ordering.** In `SpecializeCommon`, Zygote calls `setresuid()` (KSU hook sets `UMOUNTED`/`NO_SU`) **before** `selinux_android_setcontext()` (sets `UNTRUSTED_APP`). Both run in the same child. Hiding needs both flags, so the order does not matter. During the short window between the two calls, nothing is hidden, which is safe.
- **Threads created later.** arm64 `arch_dup_task_struct()` does `*dst = *src` (THREAD_INFO_IN_TASK, enforced by `BUILD_BUG_ON`). Afterwards it clears only `TIF_SVE` and `TIF_MTE_ASYNC_FAULT`, and `copy_process()` clears only `TIF_SYSCALL_TRACE` and `TIF_SYSCALL_EMU`. Bits 33–36 are inherited by new threads and by fork children.
- **Leak into Zygote.** None. The flags are only set in the post-fork child, and Zygote never runs these paths for itself. app_zygote / webview_zygote: the zygote child gets `UMOUNTED` (isolated uid), then `setcontext(app_zygote)` *clears* `UNTRUSTED_APP`. Its `isolated_app` children inherit `UMOUNTED` and set `UNTRUSTED_APP` on their own `setcontext`. Result is correct.
- `setprocattr` cannot fail after the flag write (only `commit_creds` follows), so the flags never diverge from the committed SID.
- `susfs_starts_with(str, …)` on a buffer that is not NUL-terminated (`memdup_user`) is safe in practice. The code only runs after `security_context_to_sid()` succeeded, and a valid MLS context (`u:r:T:s0…`) is always longer than the prefix and differs from it before the end of the buffer.
- The `for_each_thread` loop in `setuid_hook.c` is redundant: Zygote children are single-threaded at that point, and `selinux_setprocattr` refuses multi-threaded callers unless the transition is bounded. It is harmless.

Notes:
- **L1 (Low): race with a concurrent `clone()`.** A thread whose `dup_task_struct()` ran before the loop, but that joins the thread list after it, misses the bit. This cannot happen during Zygote specialization (single thread). It can only happen in a bounded multi-threaded `setcon`.
- **L2 (Low): exec domain transitions do not update the flag.** Example: an app crashes, the kernel goes `untrusted_app` → exec `crash_dump` (domain_auto_trans), and the uid stays ≥ 10000. `crash_dump` keeps `UNTRUSTED_APP|UMOUNTED`, so its `/proc/<pid>/maps` read is filtered and tombstones lose Lineage frames.
- **L3 (Low): domain coverage.** `ephemeral_app`, `sdk_sandbox_*` and `isolated_compute_app` are not matched (`"u:r:isolated_app"` does not match `isolated_compute_app`). Matching on the string the user wrote is also weaker than matching on the resolved SID (type aliases).

## Checklist item 3: `fs/namei.c` call sites: **PASS for refcount, RCU and loops; FAIL for B3**

| Site | Mode | Ref handling | Verdict |
|---|---|---|---|
| `lookup_dcache` L1540 | ref (`d_lookup`) | `dput` → NULL → `__lookup_hash` substitutes the fake name | OK |
| `__lookup_hash` L1587 | ref, parent locked exclusive | `dput` (callers never pass `LOOKUP_RCU`) → `d_alloc(fake)` → `retry`, `found_sus_path` stops re-checks | OK |
| `lookup_fast` RCU L1628 | no ref | no `dput`, `dentry=NULL` → `try_to_unlazy` or `-ECHILD` (restarts in ref-walk) | OK for refs, **B3** for `d_inode`/`d_name` |
| `lookup_fast` ref L1673 | ref, **parent not locked** | `dput` → NULL → `lookup_slow` | OK for refs, **B3** for `d_name` vs rename |
| `__lookup_slow` L1744 | ref, parent `i_rwsem` shared | `dput` → `d_alloc_parallel(fake)` → `retry` | OK |
| `link_path_walk` L2333 | RCU or ref | returns `-ENOENT`, no put; `terminate_walk` cleans up | OK, **B3** (should use `nd->inode`) |
| `lookup_open` L3345 | ref, parent locked | `dput`, `found_sus_path` → `d_alloc_parallel(fake)` | OK (see L7) |

`d_in_lookup()`/`d_lookup_done()` on an RCU dentry is unreachable, because `__d_lookup_rcu` never returns in-lookup dentries (they live in `in_lookup_hashtable`).

### Trace: `/product/overlay/LineageBlackTheme/...`
1. `link_path_walk`: at the top of the loop `nd->path.dentry = overlay`, which does not match. Then `may_lookup`, then `hash_name("LineageBlackTheme")`, then `walk_component(WALK_MORE)`.
2. `lookup_fast` (RCU): `__d_lookup_rcu` finds the positive dentry. `susfs_is_dentry_sus_path` returns true (uid 0, name matches). `dentry=NULL`, then `try_to_unlazy`.
   - Unlazy fails: returns `-ECHILD`, `path_lookupat` restarts without `LOOKUP_RCU`, and step 2 runs again in ref mode: `__d_lookup` (+1) → match → `dput` (−1) → NULL.
3. `lookup_slow` takes `inode_lock_shared(overlay)`, then `__lookup_slow`: `d_alloc_parallel(dir,"LineageBlackTheme")` returns the existing hashed dentry (+1), not in-lookup. `d_revalidate` (erofs has none) returns 1. The check matches, so: `dput` (−1), `d_alloc_parallel(dir,"..5.u.S")` returns a new in-lookup dentry (or the cached negative one from an earlier walk), `found_sus_path=true`, `goto retry`. Then `->lookup` → negative, `d_lookup_done`, no re-check. The negative dentry (+1) is returned.
4. `step_into` → `handle_mounts` → `traverse_mounts`: no `DCACHE_MANAGED_DENTRY` and `d_flags_negative` true, so it returns **-ENOENT**. `handle_mounts` does `dput(path->dentry)` (−1). `walk_component` returns `ERR_PTR(-ENOENT)`, and `link_path_walk` returns it.
5. Refcount is balanced. No loop: `retry` only re-enters the `IS_ERR`/revalidate block. If the fake dentry's revalidate fails, the code calls `d_invalidate`, then `dput`, then allocates a fresh in-lookup fake dentry, which takes the `->lookup` branch and exits. No crash, as long as `d_inode`/`d_name` stay stable (B3).

### B3: memory-safety races (Medium)
`fs/susfs.c:294-304`:
```c
(!dentry->d_inode || dentry->d_inode->i_uid.val < 10000) && name-match ...
return dentry->d_inode && susfs_is_inode_sus_path(dentry->d_inode);
```
- **NULL dereference race.** In RCU-walk (`lookup_fast` RCU, `link_path_walk` RCU) the walker holds no reference. `vfs_unlink` → `d_delete` → `dentry_unlink_inode` sets `d_inode = NULL` when the unlinker holds the only reference. Without `READ_ONCE`, the compiler may reload `d_inode` between the NULL test and `->i_uid` (with full LTO, inlining into namei.c is possible). The uid dereference also runs **before** the name match, so the window applies to *every* dentry an untrusted app walks, not only Lineage names. The inode memory itself stays valid under RCU (freed by call_rcu), so the only failure mode is the NULL.
- **Rename race on `d_name`.** `copy_name()`/`swap_names()` free external names with `kfree_rcu`, and `name`/`len` are separate loads.
  - `lookup_fast` ref branch and `link_path_walk` ref mode: the parent `i_rwsem` is not held and the reader is not under RCU, so a concurrent rename can produce a stale `name` pointer, which means an out-of-bounds read or a use-after-free.
  - `SUSFS_IS_VMA_FILE_SUS_MAP`: called with only `mmap_lock` held, same race.
  - Safe sites: `__lookup_slow`, `__lookup_hash` and `lookup_open` hold the parent `i_rwsem`, which blocks rename of children.
  - RCU sites are memory-safe but can read a torn name/len pair, and the decision is made before `read_seqcount_retry(&dentry->d_seq)` validates the dentry.
- Fix: read the inode once (`READ_ONCE`), check the name first, and gate on `sb_rdonly(dentry->d_sb)`. Names on a read-only superblock cannot be renamed or unlinked, which removes both races. In `link_path_walk`, use `nd->inode`.

### Behaviour change (Info)
`|| susfs_is_dentry_sus_path(dentry)` also calls `susfs_is_inode_sus_path()` **unconditionally**. This removes upstream's `LOOKUP_LAST`/`OPEN_LAST` gating for inode-flagged sus paths in `lookup_fast` and `__lookup_slow`. For directories the result is the same (`link_path_walk` would return ENOENT one step later). The difference is for an inode-flagged **symlink used as an intermediate component**: before, it was followed; now it returns ENOENT. This is probably fine, but it is a semantic change to existing SuSFS behaviour.

## Checklist item 4: `fs/readdir.c`: **PASS for locks, buffers and leaks; FAIL for B2 and B4**

- The early `return 0` comes before `ilookup()`, so nothing is held: no inode, no `user_write_access_begin`. `buf->current_dir/count/prev_reclen` are untouched, and the next emitted entry writes its `offset` into `prev->d_off`, so `telldir`/`seekdir` stay consistent. Clean skip.
- **B4.** The skip happens **after** `buf->error = -EINVAL` (L289, and the same in `filldir64`/`compat_filldir`). If one `getdents64` call reaches EOF after emitting nothing but hidden entries, `prev_reclen == 0` and the syscall returns `-EINVAL` instead of 0. An app can detect this by calling with a one-record buffer and watching the last call before EOF. Also, a hidden name that is longer than the remaining buffer still produces `-EINVAL`/"buffer too small". Fix: move the check directly after `verify_dirent_name()` and set `buf->error = 0` (getdents/getdents64/compat) before `return 0`. `fillonedir`/`compat_fillonedir` are fine (`result` stays 0).
- **B2.** The check has no superblock or owner condition, so on all filesystems (FUSE `/sdcard`, `/data`, `/proc`, tmpfs `/dev/__properties__`) it disagrees with lookup, which also checks owner uid < 10000:
  - Detection oracle: create `files/lineage_x`, `stat()` succeeds, but `readdir()` does not show it.
  - Real breakage: file managers and gallery apps cannot see `/sdcard/Download/lineage-*.zip`, and an app cannot recursively delete its own directories that contain such names.

## Checklist item 5: `task_mmu.c` / `base.c`: **PASS for NULL safety; Low gaps**

- `vma->vm_file` is pinned by the VMA. `f_path.dentry` is never NULL for a mapped file, and `file_inode(f)` is never NULL. The `(f)` NULL guard and the `f_path.dentry` guard are redundant but harmless.
- Macro precedence is correct: `SUSFS_IS_INODE_SUS_MAP` has no outer parentheses, but it sits inside `( … || (…))`, so `a&&b&&c&&d || e` evaluates as intended. The argument has no side effects.
- `d_name` is read without lock or RCU: see B3.
- **B1 also applies here**: the app's own `/data/app/...` and odex mappings disappear from its `/proc/self/maps` if its package name contains "lineage". Anti-cheat SDKs (NCSoft games) and crash symbolizers read their own maps.
- **L4 (Low):** only the basename is tested, but `show_map_vma` prints the full `d_path`. A file without "lineage" in its name inside a Lineage-named directory still leaks the directory name. Anonymous VMA names (`[anon:dalvik-…lineage…]`, for example ART boot-image spaces if Lineage jars are in BOOTCLASSPATH) are not filtered.
- **L5 (Low):** `mm/memory.c:5682` (remote VM access for `/proc/pid/mem`) still uses `SUSFS_IS_INODE_SUS_MAP`, and `proc_map_files_lookup`/`get_link` are not filtered. An app that knows an address can still read that memory or `readlink` the mapping.
- **L6 (Style):** the macro is copied into two files. Make it a `static inline` in `susfs_def.h`.

## Other findings
- **L7 (Low, existing hazard that now applies to more names):** `lookup_open` with `O_CREAT` on a hidden positive dentry swaps in `"..5.u.S"` and **creates that file** on a writable filesystem. `__lookup_hash` blocks this only for FUSE. With the patch as written this is reachable wherever a uid < 10000, app-writable directory holds a matching name. The `sb_rdonly` gate removes it, because creating on a read-only fs returns `EROFS`, which is what a missing file returns too.
- **L8 (Low, scope creep):** `fs/susfs.c:220` adds `AS_FLAGS_SUS_MAP` in the *re-flag loop* only, for non-FUSE inodes only, and does not add it when the path is first registered. As a result, map hiding for `sus_path_loop` entries depends on whether the loop has run yet. It is also unrelated to the wildcard feature. Split it into its own commit or drop it.
- **L9 (Style):** `susfs_is_dentry_sus_path` has no prototype in a header (`-Wmissing-prototypes` under W=1). Move the `extern` from namei.c into `susfs.h`.
- **Residual detection surface, out of VFS scope:** `ro.lineage.*` properties, `$BOOTCLASSPATH`/`/proc/self/environ`, PackageManager visibility of `org.lineageos.*`, and `/dev/__properties__/*lineage*` context files (hidden from lookup only when owned by uid < 10000; bionic then fails that property area quietly).

---

## Recommended fix (addresses B1, B2, B3, L7, and most of the map collateral)

```c
/* fs/susfs.c */
bool susfs_is_dentry_sus_path(struct dentry *dentry)
{
	struct inode *inode;

	if (!dentry)
		return false;
	inode = READ_ONCE(dentry->d_inode);
	if (!inode)
		return false;
	if (susfs_is_current_untrusted_umounted_app() &&
	    sb_rdonly(dentry->d_sb) &&                 /* system/vendor/product/system_ext/odm/apex only */
	    __kuid_val(inode->i_uid) < 10000 &&
	    unlikely(susfs_is_cusrom_name_len(dentry->d_name.name, dentry->d_name.len)))
		return true;
	return susfs_is_inode_sus_path(inode);
}
```
```c
/* fs/readdir.c: in each filldir*, right after verify_dirent_name() */
if (susfs_is_current_untrusted_umounted_app() && sb_rdonly(buf->sb) &&
    unlikely(susfs_is_cusrom_name_len(name, namlen))) {
	buf->error = 0;          /* (fillonedir: leave result at 0) */
	return 0;
}
```
`buf->sb` is already replaced by the `/data` superblock for FUSE, which is read-write, so `/sdcard` is excluded automatically.
```c
/* susfs_def.h: one shared helper for task_mmu.c/base.c */
static inline bool susfs_is_vma_file_sus_map(struct file *f) {
	struct inode *inode;
	if (!f) return false;
	inode = file_inode(f);
	if (SUSFS_IS_INODE_SUS_MAP(inode)) return true;
	return susfs_is_current_untrusted_umounted_app() && sb_rdonly(inode->i_sb) &&
	       unlikely(susfs_is_cusrom_name_len(f->f_path.dentry->d_name.name,
	                                          f->f_path.dentry->d_name.len));
}
```
In `link_path_walk`, check `nd->inode` instead of re-reading `dentry->d_inode`.

## On-device validation, after the fix
1. Install a package with "lineage" in its name (or `com.ncsoft.lineage2m`), launch it, and confirm it does not crash.
2. From an untrusted test app: `ls /system`, `ls /product/overlay`, `stat /system/addon.d` must return ENOENT, and `readdir` must not show the entries.
3. Call `getdents64` with a one-record buffer over `/system_ext/framework`. No call may return `EINVAL`.
4. Create and list `files/lineage_x` in the app's own data dir. It must be visible both to `stat` and to `readdir`.
5. Check that `system_server`, SystemUI, and `org.lineageos.*` (platform_app) still list Lineage paths.
6. Expect this regression even with the fix: the app process opens RRO overlay APKs itself (`ResourcesManager` → `ApkAssets.loadFromPath`). Any enabled overlay named `*Lineage*` (for example `LineageBlackTheme`) fails to load in untrusted apps. `ResourcesManager` logs a warning and skips it, so the app does not crash, but it renders without the overlay. Confirm this is acceptable, or exclude `/product/overlay` APKs (`.apk` suffix) from lookup hiding and keep readdir hiding only.
