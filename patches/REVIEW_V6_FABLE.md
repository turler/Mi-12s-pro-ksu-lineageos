Total messages: 29
--- [fable_reviewer / claude-opus-5-5] ---
Review complete. Verdict first, then evidence and exact fixes.

# VERDICT: BLOCK

Three defects are release-blocking (one system-breaking, two that make the advertised features non-functional/detectable). Section 1 (reboot migration) passes. Details below.

---

## 1. Process-context SUSFS supercall migration — PASS

Verified against `kernel/reboot.c:306/326` and `drivers/kernelsu/supercall/supercall.c:128-209`.

- **Dispatch & magic gate:** `SYSCALL_DEFINE4(reboot,...)` branches on `magic1==0xDEADBEEF && magic2==0xFAFAFAFA` and calls `ksu_susfs_handle_sys_reboot(magic1,magic2,cmd,&arg)` *before* `ns_capable(CAP_SYS_BOOT)`. Handler re-checks `KSU_INSTALL_MAGIC1`(0xDEADBEEF, `uapi/supercall.h:16`) / `SUSFS_MAGIC`(0xFAFAFAFA, `susfs_def.h:12`). Consistent.
- **Atomic→process fix (a):** Confirmed. The handler now runs in the syscall body (process context), so `susfs_add_open_redirect`/`susfs_add_sus_kstat_redirect` legally call `kern_path`, `kzalloc(GFP_KERNEL)`, `mutex_lock`, `synchronize_rcu`. The old kprobe `reboot_handler_pre` (`supercall.c:212`) no longer touches `SUSFS_MAGIC` — it only handles `KSU_INSTALL_MAGIC2`(0xCAFEBABE)/`CHANGE_*`, so no sleeping-in-atomic and no double-dispatch.
- **-EINVAL→0 fix (b):** Confirmed. Handled commands `return 0` from the syscall, so `SYS_reboot` returns 0 and the Rust `SusfsClient::probe()` (`susfsd.rs:231` reads `cmd.err`) succeeds instead of getting -EINVAL from the real reboot path.
- **`&arg` type match:** Confirmed. `arg` is `void __user *`; `&arg` is `void __user **`; every `susfs_*` handler does `copy_from_user(&info, *user_info, ...)`, i.e. `*user_info == arg ==` user payload pointer. Correct.

One nit (non-blocking): the handler's `default: return 0` swallows unknown commands as success rather than leaving the userspace `ERR_CMD_NOT_SUPPORTED`(126) sentinel intact (the LKM variant in `susfs_supercall.c:254` deliberately does *not* hijack unknown cmds). Harmless for current clients but drops the "feature-absent" signal.

---

## 2. ZeroMount VFS driver — BLOCK

### 2a. CRITICAL — getdents/getdents64/compat return 0 bytes for real directories (`fs/readdir.c:389-419`, and the two siblings)

The injection block is entered on **every** successful iterate, and it `goto zm_out` **unconditionally**, skipping the entry-finalization block:

```c
	error = iterate_dir(f.file, &buf.ctx);
	if (error >= 0)
		error = buf.error;                 /* == 0 on success */
#ifdef CONFIG_ZEROMOUNT
skip_real_iterate:
	if (error >= 0 && !signal_pending(current)) {
		zeromount_inject_dents(f.file, (void __user **)&dirent, &count, &f.file->f_pos);
		if (count != initial_count)
			error = initial_count - count; /* only injected bytes */
		goto zm_out;                       /* <-- skips the block below */
	}
#endif
	if (buf.prev_reclen) {                 /* NEVER runs when ZEROMOUNT=y */
		...
		error = count - buf.count;         /* the real byte count */
	}
```

Consequences with `CONFIG_ZEROMOUNT=y` (it is, `out-ksu/.config:7016`):
- Normal directory, no injected children (the overwhelming case, and the case even when ZeroMount is *disabled* — the `goto` doesn't consult `zeromount_enabled`): `count==initial_count`, so `error` stays `buf.error==0`. The syscall returns **0 → userspace sees EOF**, discarding every real entry that `filldir` already wrote. `ls` of any directory is empty; init/zygote directory scans fail. This is a boot-breaker.
- The last real dirent's `d_off` is never written (`put_user(buf.ctx.pos,&lastdirent->d_off)` skipped).
- Injection also writes at the *base* `dirent`, not at `buf.current_dir`, so on a real dir that *does* have injected children it clobbers the real entries and still mis-reports the count.

Your specific question — *is `zm_out:` before `fdput_pos(f)` and the SUS_PATH `path_put`?* — **Yes, placement is correct; there is no fd or path leak.** The bug is the control flow reaching it, not the label position.

**Exact fix (apply identically to `SYSCALL_DEFINE3(getdents64)` with `linux_dirent64`, and `COMPAT_SYSCALL_DEFINE3(getdents)` with `compat_linux_dirent`/`zeromount_inject_dents`):**

```c
	error = iterate_dir(f.file, &buf.ctx);
	if (error >= 0)
		error = buf.error;

#ifdef CONFIG_ZEROMOUNT
skip_real_iterate:
#endif
	if (buf.prev_reclen) {
		struct linux_dirent __user *lastdirent;
		lastdirent = (void __user *)buf.current_dir - buf.prev_reclen;
		if (put_user(buf.ctx.pos, &lastdirent->d_off))
			error = -EFAULT;
		else
			error = count - buf.count;
	}

#ifdef CONFIG_ZEROMOUNT
	if (error >= 0 && !signal_pending(current)) {
		void __user *inj = buf.current_dir;   /* append AFTER real entries */
		int inj_count = buf.count;            /* remaining buffer space    */

		zeromount_inject_dents(f.file, &inj, &inj_count, &f.file->f_pos);
		if (inj_count != buf.count)
			error += buf.count - inj_count;   /* add injected byte count   */
	}
#endif
	fdput_pos(f);
```

Remove the now-unused `initial_count`. On the `skip_real_iterate` (fully-virtual, `f_pos>=ZEROMOUNT_MAGIC_POS`) entry, `buf.prev_reclen==0`, `buf.current_dir==dirent`, `buf.count==count`, `error==0`, so injection starts at the buffer base exactly as before and `error` becomes the injected byte count. Both paths are now correct.

### 2b. HIGH (design) — ZeroMount is globally disabled for exactly its target processes

`zeromount_should_skip()` (`fs/zeromount.c:110`) returns true when `susfs_is_current_proc_umounted()` (== `TIF_PROC_UMOUNTED`, `susfs_def.h:125`). `setuid_hook.c:52` sets `TIF_PROC_UMOUNTED` on **every** zygote-spawned app that `ksu_uid_should_umount()` selects (default: all non-allowlisted apps), and `selinux/hooks.c:6579` additionally flags all `untrusted_app`/`isolated_app` with `TIF_PROC_UNTRUSTED_APP`.

So for an `untrusted_app` opening `/system/etc/fonts.xml`, `/system/fonts/Roboto-Regular.ttf`, or reading `/proc/self/maps`:
- `zeromount_getname_hook`, `zeromount_stat_hook`, `zeromount_inject_dents*`, `zeromount_spoof_statfs`, `zeromount_spoof_xattr`, `zeromount_is_injected_file`, `zeromount_is_traversal_allowed` all early-return (both via `should_skip()` *and* their own redundant `susfs_is_current_proc_umounted()` guards at `:334/465/488/521/632/668/834/907`).
- Result: the app sees **neither** the (unmounted) module overlay **nor** any ZeroMount redirect/injection. Every file ZeroMount is meant to serve systemlessly is invisible to normal apps, and `/proc/self/maps` dev/ino is not spoofed for them.

If the intent is "hide modules from untrusted apps only," this is merely redundant (the per-call `susfs_*` guards duplicate `should_skip`). If the intent is "serve injected content to apps while staying undetectable," it is wrong: it must gate on the per-UID list, not the global umount flag.

**Recommendation:** drop the global `TIF_PROC_UMOUNTED` skip from `zeromount_should_skip()` and the duplicated per-function `susfs_is_current_proc_umounted()` early-returns; rely on `zeromount_is_uid_blocked(current_uid().val)` (already called at every site) plus an explicit opt-out list populated for processes that must see the pristine tree. Concretely, in `zeromount_should_skip()` delete:

```c
#ifdef CONFIG_KSU_SUSFS
	if (susfs_is_current_proc_umounted())
		return true;
#endif
```

and remove the identical blocks in `zeromount_get_virtual_path_for_inode`, `zeromount_is_traversal_allowed`, `zeromount_is_injected_file`, `zeromount_resolve_path`, `zeromount_getname_hook`, `zeromount_inject_dents_common`, `zeromount_spoof_statfs`, `zeromount_spoof_xattr`. Keep exclusion entirely in `zeromount_is_uid_blocked()`. (If some trusted UIDs must be skipped, add them to the uid block list at setup.)

### 2c. MEDIUM — `android_oem_data1` bit 0 recursion guard: collision risk

`current->android_oem_data1` is `u64[32]` (`sched.h:1387`). The guard uses bit 0 of element [0] (`zeromount.h:27-43`). Within this tree only `init_task.c:218` initializes it and nothing else reads/writes it, and SuSFS does **not** use it — so no in-tree conflict. But `android_oem_data1[0]` is GKI vendor scratch space; an OEM vendor-hook module (scheduler/IO/thermal) may legitimately store a pointer or flags there, and bit 0 of a stored pointer/counter would alias ZeroMount's guard → false "recursive" (ZeroMount silently no-ops) or a clobbered vendor value. Non-blocking on this source tree, but document the assumption or switch to a dedicated `TIF_` bit / a `task_struct` field you own, consistent with how SuSFS uses `TIF_PROC_*`.

### 2d. Minor (non-blocking)
- `zeromount_get_static_vpath` (`:359`) runs in `d_path()` for **all** callers (no `should_skip`/uid gate), so root/system also get the `/system`-prefixed spoofed path for a redirected inode. Intentional for consistency, but be aware it is not limited to target apps. Allocation is `GFP_ATOMIC` and freed on both branches — no leak.
- SAR resolution in `zeromount_ioctl_add_rule` (`:1112`, `:1168`) correctly tries `v_path_raw` (`/system/...`) before the normalized `v_path`; `v_path_raw` is freed once at `:1177`. OK.

---

## 3. Enhanced SuSFS Kstat Redirect — BLOCK

### 3a. ABI layout — PASS
`struct st_susfs_sus_kstat_redirect` (`susfs.h:1304`) with `SUSFS_MAX_LEN_PATHNAME==256` (`susfs_def.h:39`), aarch64 LP64:
`virtual_pathname`@0 (256), `real_pathname`@256 (256), `spoofed_ino`@512, `spoofed_dev`@520, `spoofed_nlink`@528, (pad 4), `spoofed_size`@536, atime/mtime/ctime sec@544/552/560, atime/mtime/ctime nsec@568/576/584, `spoofed_blksize`@592, `spoofed_blocks`@600, `err`@**608**, tail pad → **sizeof==616**. Matches the Rust `StSusfsSusKstatRedirect` (616; offsets 0, 256, 512..608). No `BUILD_BUG_ON` guards this struct though — add one for safety:
```c
BUILD_BUG_ON(sizeof(struct st_susfs_sus_kstat_redirect) != 616);
BUILD_BUG_ON(offsetof(struct st_susfs_sus_kstat_redirect, err) != 608);
```

### 3b. CRITICAL — redirect entry leaves `info.flags`, `spoofed_mnt_id`, `spoofed_kstatfs` uninitialized (`fs/susfs.c:551-668`)

`susfs_add_sus_kstat_redirect` `kzalloc`s the hlist entry and fills `info.spoofed_*` by name, but never sets:

1. **`new_entry->info.flags`** — stays 0. The stat consumer `susfs_sus_kstat_spoof_generic_fillattr` (`:782-805`) applies each field **only** under `if (entry->info.flags & KSTAT_SPOOF_*)`. With flags==0, `stat()`/`statx()` on the redirected inode spoofs **nothing** (ino, dev, nlink, size, times all pass through real values). The feature is inert for its primary syscall.
2. **`new_entry->spoofed_mnt_id`** — stays 0, but `:807` writes it **unconditionally** (`stat->mnt_id = entry->spoofed_mnt_id;`). So the only visible effect of a redirect is that `stat->mnt_id` becomes **0** for the real file — wrong *and* a detection signal (real files never have mnt_id 0).
3. **`new_entry->spoofed_kstatfs`** — stays all-zero. The redirect sets `AS_FLAGS_SUS_KSTAT`, so for an app-uid `statfs()`/`fstatfs()` on the redirected path hits `susfs_sus_kstat_spoof_vfs_statfs` (`:867`) → `memcpy(buf,&entry->spoofed_kstatfs,...)` → returns a **zeroed `kstatfs`** (f_type/f_bsize/f_blocks all 0). Confirmed reachable via `fs/statfs.c:108` and `:142-148` (`susfs_is_current_app_uid()` + `susfs_is_inode_sus_kstat`).
4. **`is_fuse`** — 0 by `kzalloc`, acceptable for erofs/ext4/f2fs targets, but then it is never recomputed; a FUSE (`/data`) target would mismatch the `entry->is_fuse==is_fuse` check in the stat/map consumers (`:778/847`) and silently not spoof. Set it from the real inode's `s_magic`.

**Exact fix** — after resolving `p_real` (replace the block at `:622-638`):

```c
	new_entry->target_ino  = inode_real->i_ino;
	new_entry->target_dev  = inode_real->i_sb->s_dev;
	new_entry->is_fuse     = (inode_real->i_sb->s_magic == FUSE_SUPER_MAGIC);
	new_entry->spoofed_mnt_id =
		susfs_get_non_sus_mnt_id_from_mnt(real_mount(p_real.mnt));
	{
		struct vfsmount *no_sus = susfs_get_non_sus_vfsmnt_from_vfsmnt(p_real.mnt);
		if (no_sus) {
			if (!statfs_by_dentry_wrapper(no_sus->mnt_root,
						      &new_entry->spoofed_kstatfs))
				new_entry->spoofed_kstatfs.f_flags =
					calculate_f_flags_wrapper(no_sus);
			dput(no_sus->mnt_root);
			mntput(no_sus);
		}
	}

	new_entry->info.is_statically = 0;
	new_entry->info.target_ino    = inode_real->i_ino;
	strscpy(new_entry->info.target_pathname, info.virtual_pathname,
		SUSFS_MAX_LEN_PATHNAME);
	new_entry->info.spoofed_ino   = info.spoofed_ino;
	new_entry->info.spoofed_dev   = info.spoofed_dev;
	new_entry->info.spoofed_nlink = info.spoofed_nlink;
	new_entry->info.spoofed_size  = info.spoofed_size;
	new_entry->info.spoofed_atime_tv_sec  = info.spoofed_atime_tv_sec;
	new_entry->info.spoofed_mtime_tv_sec  = info.spoofed_mtime_tv_sec;
	new_entry->info.spoofed_ctime_tv_sec  = info.spoofed_ctime_tv_sec;
	new_entry->info.spoofed_atime_tv_nsec = info.spoofed_atime_tv_nsec;
	new_entry->info.spoofed_mtime_tv_nsec = info.spoofed_mtime_tv_nsec;
	new_entry->info.spoofed_ctime_tv_nsec = info.spoofed_ctime_tv_nsec;
	new_entry->info.spoofed_blksize = info.spoofed_blksize;
	new_entry->info.spoofed_blocks  = info.spoofed_blocks;
	/* REQUIRED: tell the consumers which fields to spoof */
	new_entry->info.flags =
		KSTAT_SPOOF_INO | KSTAT_SPOOF_DEV | KSTAT_SPOOF_NLINK |
		KSTAT_SPOOF_SIZE |
		KSTAT_SPOOF_ATIME_TV_SEC | KSTAT_SPOOF_ATIME_TV_NSEC |
		KSTAT_SPOOF_MTIME_TV_SEC | KSTAT_SPOOF_MTIME_TV_NSEC |
		KSTAT_SPOOF_CTIME_TV_SEC | KSTAT_SPOOF_CTIME_TV_NSEC |
		KSTAT_SPOOF_BLKSIZE | KSTAT_SPOOF_BLOCKS;
```

(If a zero `spoofed_*` field should mean "don't spoof," have userspace pass a flags mask in the ABI instead of hardcoding; either way, flags must not stay 0.)

### 3c. MEDIUM — `virtual_entry->target_dev` set to `spoofed_dev`, breaking its own lookup (`:651`)

```c
	virtual_entry->target_ino = virtual_ino;              /* real ino of vpath - OK  */
	virtual_entry->target_dev = new_entry->info.spoofed_dev; /* WRONG */
```
Consumers match on `entry->target_dev == inode->i_sb->s_dev` where that is the virtual inode's **real** device. Setting `target_dev = spoofed_dev` means the virtual entry only matches if the real device already equals the spoofed one — normally never — so the virtual-path entry is dead. Use the resolved virtual inode's real dev:

```c
	virtual_entry->target_dev = inode_virtual->i_sb->s_dev;
```
(capture it alongside `virtual_ino` at `:591` before `path_put(&p_virtual)`), and also set `virtual_entry->info.flags` (via the `memcpy` from `new_entry->info` this now inherits the mask from 3b — good) and `virtual_entry->is_fuse`/`spoofed_mnt_id`/`spoofed_kstatfs` from the virtual inode.

### 3d. MEDIUM — no duplicate handling; re-add leaks and shadows (`:655-660`)

Unlike `susfs_add_sus_kstat` (`:467-505`, which finds a same-pathname entry, `hash_del_rcu` + `synchronize_rcu` + `kfree` before re-adding), the redirect path does a bare `hash_add_rcu` with no dedupe. ksud re-running the supercall (boot re-apply, module reload) appends **duplicate** entries keyed on the same `target_ino`: the stale entries are never freed (leak, and there is no clear/remove path for kstat entries) and `hash_for_each_possible_rcu` returns whichever matches first, which may be a stale spoof. Add the same remove-first logic under `susfs_mutex_lock_sus_kstat`:

```c
	mutex_lock(&susfs_mutex_lock_sus_kstat);
	{
		struct st_susfs_sus_kstat_hlist *dup;
		struct hlist_node *tmp;
		hash_for_each_possible_safe(SUS_KSTAT_HLIST, dup, tmp, node,
					    new_entry->target_ino) {
			if (!strcmp(dup->info.target_pathname,
				    new_entry->info.target_pathname)) {
				hash_del_rcu(&dup->node);
				/* defer free after grace period */
				hash_add_rcu(SUS_KSTAT_HLIST, &new_entry->node,
					     new_entry->target_ino);
				if (virtual_entry)
					hash_add_rcu(SUS_KSTAT_HLIST,
						     &virtual_entry->node, virtual_ino);
				mutex_unlock(&susfs_mutex_lock_sus_kstat);
				synchronize_rcu();
				kfree(dup);
				goto added;
			}
		}
	}
	hash_add_rcu(SUS_KSTAT_HLIST, &new_entry->node, new_entry->target_ino);
	if (virtual_entry)
		hash_add_rcu(SUS_KSTAT_HLIST, &virtual_entry->node, virtual_ino);
	mutex_unlock(&susfs_mutex_lock_sus_kstat);
added:
```
(Dedup the virtual entry on `virtual_ino` the same way, or accept that the virtual key rarely collides.)

---

## Summary of required fixes before merge

| # | File | Severity | Issue |
|---|------|----------|-------|
| 2a | fs/readdir.c (×3 syscalls) | BLOCK | Unconditional `goto zm_out` skips finalization → getdents returns 0; directories read as empty |
| 3b | fs/susfs.c:622 | BLOCK | redirect entry never sets `info.flags`/`spoofed_mnt_id`/`spoofed_kstatfs`/`is_fuse` → stat spoof inert, mnt_id=0, statfs zeroed |
| 2b | fs/zeromount.c:110 (+8 sites) | HIGH | global `TIF_PROC_UMOUNTED` skip disables ZeroMount for all target apps; use per-UID list |
| 3c | fs/susfs.c:651 | MEDIUM | `virtual_entry->target_dev = spoofed_dev` → virtual entry never matches |
| 3d | fs/susfs.c:655 | MEDIUM | no duplicate removal → leak + stale spoof on re-add |
| 2c | include/linux/zeromount.h:27 | MEDIUM | `android_oem_data1` bit0 may alias GKI vendor-hook data |
| 3a | susfs_supercall abi check | LOW | add `BUILD_BUG_ON` for the 616/608 redirect layout |

Section 1 passes as-is. Sections 2 and 3 must not ship until 2a and 3b (minimum) are fixed; 2a alone prevents boot with `CONFIG_ZEROMOUNT=y`.

Next: apply the `fs/readdir.c` fix (2a) to all three syscalls, then the `fs/susfs.c:622` field-init fix (3b), and rebuild `out-ksu`.
