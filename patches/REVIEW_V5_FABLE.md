Total messages: 38
--- [fable_reviewer / claude-opus-5-5] ---
**Verdict: PASS_WITH_FIXES.** The kernfs hunk is correct and the script fix is correct, but the v5 images on disk now are still the broken build. Do not flash `out/boot_ksun_susfs_v5.img` or the Desktop copy. Run the fixed `do_build_v5.sh` first.

The current `out-ksu/vmlinux` (built 21:11) is `Type: EXEC`, and both `.relr.dyn` and `.rela.dyn` are size 0. The stock-equivalent `out-base` build is `DYN` with `ANDROID_RELR` size 0x8718. `.vmlinux.cmd` shows the link used only `"--threads=4"` as `LDFLAGS_vmlinux`. `fs/kernfs/file.o` was rebuilt at 21:27, after that link, so the charge hunk is not in the current Image either.

## 1. kernfs hunk (`__kernfs_create_file`): PASS

**a) Does the path reach the hunk with the right names? Yes.**
- `class_register` → `__class_register` → `kobject_set_name(cls->name)` gives "qcom-battery" → `kset_register` → `class_add_groups` → `sysfs_create_groups(&cp->subsys.kobj)`.
- Neither `battery_class_group` nor `xiaomi_battery_class_group` has a `.name`, so `kn = kobj->sd` (the `qcom-battery` directory node).
- `create_files` → `sysfs_add_file_mode_ns(..., mode & 0777)` → `__kernfs_create_file(parent = qcom-battery node, name = "input_suspend")`. `input_suspend` is in `xiaomi_battery_class_attrs`.
- The driver is a module (`=m`), but this code is in vmlinux, so the stock vendor `.ko` goes through it too.

**b) Are `parent` and `parent->name` safe? Yes.**
- `sysfs_add_file_mode_ns` already dereferences `parent->priv`, and `kernfs_new_node` dereferences `parent->mode`, so the `parent &&` check is redundant but harmless.
- `internal_create_group` holds a `kernfs_get(kn)` on the parent.
- `parent->name` is `kstrdup_const` and only changes through `kernfs_rename_ns`, which never happens for a class kset.
- The read is unlocked, but `strcmp(name,"input_suspend")` short-circuits first, so other kernfs users (for example renamed cgroups) never reach that read.

**c) Locking and ueventd: clean.**
- The new node is not yet linked or activated (`KN_DEACTIVATED_BIAS`). `__kernfs_setattr` → `kernfs_iattrs` takes only `iattr_mutex`, in sleepable probe context. This is the same path every non-root-owned sysfs file uses.
- If ueventd later runs chown/chmod, it goes through `kernfs_iop_setattr` → `kernfs_setattr` under `kernfs_mutex` and sets the same values, so it is a no-op.
- Why the hunk is actually needed: `ueventd.qcom.rc:509` already requests `0660 system system`. But `kset_register` sends KOBJ_ADD *before* `class_add_groups` creates the files, so ueventd races to chown a file that does not exist yet. The class directory has no `uevent` file, so coldboot cannot replay it. The hunk closes that race.
- 0660 removes world-read compared with stock 0644, but that matches what the ROM itself asks for.

**d) KMI and SELinux: no impact.**
- The function signature is unchanged and `__kernfs_create_file` is not in `vmlinux.symvers`. Bit 36 is unused on arm64 and `ti->flags` is 64-bit.
- SELinux labels come from the path (`security_kernfs_init_security`), not from DAC owner or mode, so the genfscon label is unchanged.

## 2. Other hunks (unchanged from v4)

The only difference between v4 and v5 is the kernfs hunk.

| Area | Result |
|---|---|
| binder bounds (both passes, UTF-16 scans, 512 B stack buffer) | Correct. Frames measured: scrub function 0x220+0x60, not inlined into `binder_transaction` (0x1c0+0x60) |
| binder hook placement | After all data copies, no locks held, so `kvmalloc(GFP_KERNEL)` is OK |
| `for_each_thread` under RCU, atomic `set_ti_thread_flag` | OK |
| `susfs_is_priority_uid_filtered`, `get_anon_bdev`, readdir, proc maps | OK |
| Graft patch dependency | `ksun-work` has staged changes that `git diff` (Step 7) does not export. They are covered by `0001-Graft-SuSFS-v2.3.0-Equinox-recipe.patch`, so v5 depends on that patch being applied first |

Findings, by priority:
1. **Should fix: binder reply branch (`binder.c` ~line 3148).** `context->binder_context_mgr_node->proc` is reloaded without a lock after the NULL check. It is set to NULL at line 6460 when servicemanager dies, so a reply racing with servicemanager death can dereference NULL. Fix: check `susfs_is_task_untrusted_umounted_app` and the header first, then:
   ```c
   mutex_lock(&context->context_mgr_node_lock);
   mgr = context->binder_context_mgr_node;
   is_sm = mgr && mgr->proc == proc;
   mutex_unlock(&context->context_mgr_node_lock);
   if (!is_sm) return;
   ```
2. **Low: name read can tear during rename.** `susfs_is_dentry_sus_path` and `susfs_is_vma_file_sus_map` read `d_name.name` and `.len` separately. A concurrent rename can produce a mismatched pair and an out-of-bounds `memcmp` read (no fault, but KASAN would flag it). This only matters on rw `/data` idmaps.
3. **Behaviour risk, by design:** with KSU's default "umount for all apps", every untrusted_app gets the following. This came in with v4.
   - `getService("profile"/"*lineage*")` returns null.
   - Path components containing `lineage` owned by uid < 10000 are hidden. v4 dropped the last-component-only check, so this now applies to every component.
   - `*lineage*@idmap` files are hidden.

   Non-platform-signed Lineage apps that use lineage-sdk, and Lineage runtime overlays, may misbehave inside those apps.

## 3. `do_build_v5.sh`: correct, needs hardening

- **The awk field is correct.** For `[32] .relr.dyn ANDROID_RELR <Addr> <Off> <Size>`, `$6` is Size (0x8718 on base). It only works because the index has two digits; `[ 9]` would split into two fields.
- **Removing the override is the right fix.** It brings back `-shared -Bsymbolic -z notext`, `--pack-dyn-relocs=relr --use-android-relr-tags`, `--fix-cortex-a53-843419`, `--build-id=sha1` and `--gc-sections`. Deleting `vmlinux` and `.vmlinux.cmd` forces a relink, and `make Image` rebuilds every file that includes `susfs_def.h`.

Recommended changes:
1. Add an ELF type check after Step 3. EXEC is the actual failure signature:
   ```bash
   llvm-readelf -h out-ksu/vmlinux | grep -q 'Type:.*DYN' || { echo "FATAL: vmlinux not PIE"; exit 1; }
   ```
2. Make the size parse independent of field position:
   ```bash
   awk '/\.relr\.dyn/{for(i=1;i<=NF;i++) if($i=="ANDROID_RELR") print $(i+3)}'
   ```
3. Step 4: with `pipefail`, a non-empty `diff` makes `ABI_DIFF=$(...)` abort silently, without the FATAL message. It still fails safe. Use `cmp -s base ksu || { echo FATAL...; exit 1; }` instead.
4. If the full-LTO link runs out of memory again, limit threads with `LD="ld.lld --threads=4"`. Never override `LDFLAGS_vmlinux` on the command line.
5. Minor: line 47 copies to `Desktop/`, not `Desktop/mi 12s pro/lineageos/` as BRIEF.md says.

Next: run `bash ~/kbuild/do_build_v5.sh` (about 20–40 min for the full-LTO link at -j2), then check that `llvm-readelf -h out-ksu/vmlinux` reports `DYN` before flashing.
