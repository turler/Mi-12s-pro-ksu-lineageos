# REPORT_GOLD — gold (Redmi Note 13 5G) GKI android15-6.6.143 + KernelSU-Next v3.4.2 + SuSFS v2.3.0

Nothing was flashed. All work in `/home/minhdc/kbuild-gold`.

## Step 1 — reset + apply custom patches
- `git -C kernel checkout -- .` (back to `e9ba38a48ac0`).
- `scripts/apply_gold_custom.py` initially FAILED on 6.6.143 sources (script/tree mismatch, not a tree bug):
  1. `fs/namei.c`: the `is_nd_state_lookup_last_and_open_last` block exists twice (RCU + non-RCU branch of `lookup_fast`); script had two identical single-match edits.
  2. `fs/readdir.c`: `fillonedir` and `compat_fillonedir` share an identical preamble (`d_ino = ino;`; script expected `compat_d_ino`).
- Fix (script only): `edit()` got a `count` param (default 1); namei block -> one edit with `count=2` (duplicate edit removed); readdir onedir -> `count=2` (separate compat edit removed); final `p_rd.write_text(s_rd)`.
- Rerun output: `ALL CUSTOM PATCHES APPLIED CLEANLY`.

Diffstat (10 files, +488 / -24): binder.c, kernelsu/feature/selinux_hide.c, kernelsu/hook/setuid_hook.c, fs/namei.c, fs/proc/base.c, fs/proc/task_mmu.c, fs/readdir.c, fs/susfs.c, include/linux/susfs_def.h, security/selinux/hooks.c.

## Step 2 — diff review + build
- Reviewed diff: all 5 readdir actors guarded (`return true` skips entry, `buf->error`/`result` stay 0), `susfs_is_dentry_sus_path` declared in namei.c and defined in susfs.c under `CONFIG_KSU_SUSFS_SUS_PATH`, all new TIF/for_each_thread code under `CONFIG_KSU_SUSFS`, binder scrub bounds-checked (dsize, slen, alignment).
- `scripts/build.sh final configs/ksu-susfs.config`: rc=0 (log `build_final.log`).
- Warning check: touched all 10 changed files, rebuilt `Image` (recompiled namei/readdir/binder/susfs/selinux etc.): rc=0, 0 `warning`/`error` lines (`build_final_warn.log`).
- Committed on branch `gold-ksun-susfs`: `c5b7de84d708 gold: custom 6.6.143 SuSFS adaptations (...)`; tree clean afterwards.

## Step 3 — verification
- `llvm-readelf -h -S work/final/vmlinux`:
  - `Type: DYN (Shared object file)`
  - `[33] .relr.dyn RELR ffffffc082150a18 2150a18 00a5e0 08 A 0 0 8` -> size 0xa5e0 = 42464 bytes (> 16384 OK)
- `modcrc.py stock/CPU_DVFS.ko work/final/vmlinux.symvers`:
  `TOTAL=88 VMLINUX_MATCH=78 MISMATCH=0 EXTERNAL=10` (10 externals are vendor module deps: mt_ppm_*, mtk_ipi_*, get_mcupm_ipidev, aee_kernel_exception_api_func, ppm_cpufreq_*) -> 100% CRC match on all vmlinux-provided symbols (incl. `module_layout 0x4e276f37 OK`).
- `work/base/vmlinux.symvers` vs `work/final/vmlinux.symvers`: `cmp` -> IDENTICAL (9309 lines each, no diff).
- `work/final/include/config/kernel.release`: `6.6.143-android15-8-g1a04d7d18c1d-ab16867777-4k`

## Step 4 — packaging
- `magiskboot unpack` stock/boot.img: HEADER_VER 4, KERNEL_FMT gzip, RAMDISK_SZ 0, VBMETA preserved. Replaced `kernel` with `work/final/arch/arm64/boot/Image` (37132800 B), `magiskboot repack`.
- `out/boot_gold_ksun_susfs.img` (67108864 B = stock size, KERNEL_SZ 14742467 gz). sha256 `316733c99007c7fa4076652ad3a4b4d61ff5fb12490e3e580ea1f4002017ab9a`.
- Test: `magiskboot unpack` in `/tmp/kilo/gold_verify` succeeded (HEADER_VER 4, KERNEL_SZ 14742467); extracted `kernel` is `cmp`-identical to built Image (KERNEL_MATCH).
- `out/AnyKernel3-gold-ksun-susfs.zip` (17903679 B, 18 entries), based on `AnyKernel3-unicorn-ksun-susfs-v5.zip` layout: `Image` replaced with new Image; `anykernel.sh` updated: `device.name1=gold`, `BLOCK=boot` (unchanged), kernel string/ui_print `6.6.143-android15-8-g1a04d7d18c1d`. sha256 `ac4b8a4ae6064fcfd58407da36e26fddaf9059148578ff80b90c641dc23bfaed`.

## Step 5 — patches
- `patches/0001-ksu-susfs.patch` = `git diff 1a04d7d18c1d..e9ba38a48ac0` (22455 lines)
- `patches/0002-gold-custom.patch` = `git diff e9ba38a48ac0..HEAD` (810 lines); `git apply --check -R` on HEAD passes.

## Notes / not verified
- No on-device test (no flashing by instruction).
- `kernel/reboot.c` process-context `SYS_reboot` dispatch fix mentioned in BRIEF_GOLD.md is not part of `apply_gold_custom.py` and was not applied here.
- AnyKernel3 ui_print still shows the inherited `KSUN : v3.4.2 (33355)` line from the unicorn zip.

## Round 2 — fable_reviewer fixes (commit `0ce748ad79fb` on `gold-ksun-susfs`, on top of `c5b7de84d708`)
- Medium: `kernel/reboot.c` SuSFS shortcut now `magic1 == 0xDEADBEEF && magic2 == 0xFAFAFAFA && uid_eq(current_uid(), GLOBAL_ROOT_UID)`; non-root falls through to the normal `CAP_SYS_BOOT` check (-EPERM). `drivers/kernelsu/supercall/supercall.c` `ksu_susfs_handle_sys_reboot` now returns `-EPERM` (was `0`) for non-root (defense in depth).
- Low: added `susfs_is_cusrom_name_nul()` / `susfs_is_cusrom_idmap_nul()` in `include/linux/susfs_def.h` (`strnlen(name, NAME_MAX)` then the existing `_len` helper); `susfs_is_dentry_sus_path` (fs/susfs.c) and both `susfs_is_vma_file_sus_map` (fs/proc/base.c, fs/proc/task_mmu.c) now read only `READ_ONCE(dentry->d_name.name)` (no `d_name.len`). `_len` helpers unchanged and still used by fs/readdir.c.
- Build: `scripts/build.sh final configs/ksu-susfs.config` rc=0, 0 warning/error lines (`build_fixes.log`); susfs.o/base.o/task_mmu.o/reboot.o recompiled.
- `llvm-readelf`: `Type: DYN`; `.relr.dyn` size 0xa5e0 = 42464 B (> 16384 OK).
- `modcrc.py`: `TOTAL=88 VMLINUX_MATCH=78 MISMATCH=0 EXTERNAL=10` (`module_layout 0x4e276f37 OK`).
- `cmp work/base/vmlinux.symvers work/final/vmlinux.symvers`: IDENTICAL.
- `kernel.release`: `6.6.143-android15-8-g1a04d7d18c1d-ab16867777-4k`.
- Repack: `magiskboot unpack` of `out/boot_gold_ksun_susfs.img` OK (HEADER_VER 4, KERNEL_SZ 14743072, gzip, VBMETA); extracted `kernel` `cmp`-identical to built Image (KERNEL_MATCH). AnyKernel3 zip `Image` also cmp-identical (18 entries).
- `patches/0002-gold-custom.patch` re-exported = `git diff e9ba38a48ac0..HEAD` (840 lines, 12 files, +494/-26); `git apply --check -R` passes.
- sha256:
  - `out/boot_gold_ksun_susfs.img` `55463420437d4de02f2273474fd45943ec16979571aa9d35a7dd1f6e09d21e6b` (67108864 B)
  - `out/AnyKernel3-gold-ksun-susfs.zip` `37023fb5d6c37e5b21e140d93b09e4fa6ad820d74503b9529ca1235e1061bdd9` (17952586 B)
  - `work/final/arch/arm64/boot/Image` `2f3e18148ca05003aebe03aa36f3104b0099605a117665c1c792bd0faa640c98`
  - `patches/0002-gold-custom.patch` `1b61948c586c3a02832cc1ba9fef8e88c364691adfe8d0d7fd94d55780ebe3bc`
- Not flashed; no on-device test. Notes above regarding `kernel/reboot.c` "not applied" in Round 1 are superseded: the reboot.c hook is present in HEAD (and now root-gated).
