# spes — Redmi Note 11 (2201117TG) · Kernel 4.19.325 + KernelSU-Next + SuSFS v1.5.5

Bộ kernel tự build, chuỗi patch và module đi kèm cho **Xiaomi Redmi Note 11 (`spes`, SM6225 / Bengal)** chạy **LineageOS 24 (Android 17, API 37)**, đã kiểm thử thực tế **VNeID vượt sạch lỗi 05 / 012** và **Duck Detector xanh SELinux / Kernel / Bootloader / Mount / Zygisk / PIF**.

- **Thiết bị:** Xiaomi Redmi Note 11 (`2201117TG`, codename `spes`, A/B, boot header v3)
- **ROM:** LineageOS `24.0-20261011-UNOFFICIAL-spes` (Android 17, SDK 37, `arm64-v8a`)
- **Base kernel:** `Shaddowalker-26/android_kernel_xiaomi_spes` nhánh `prebuilt`, commit `85a26e961233` (`v4.19.325-cip137`)
- **Root:** KernelSU-Next nhánh `legacy` (commit `e5f5ec998de8`, UAPI v6, manual hook — dùng Manager CI build v3.4.2-292+ UAPI v6)
- **SuSFS:** `simonpunk/susfs4ksu` nhánh `kernel-4.19`, commit `001e69919c62` (`v1.5.5 NON-GKI`)
- **Kernel release (build `#8`):** `4.19.325-cip137-st21` (đã bỏ hậu tố `-Lineage` trực tiếp trong `kernel/localversion`, không cần spoof runtime)
- **Toolchain:** Ubuntu Clang 14.0.0 (`LLVM=1 LLVM_IAS=1`)

---

## Nội dung thư mục

```
spes-redmi-note-11/
├── README.md                                                              ← file này
├── SHA256SUMS                                                             ← checksum kiểm chứng toàn bộ artifact
├── kernel/
│   └── boot_spes_ksun_susfs_v8.img                                        ← boot image hoàn chỉnh (#8, header v3, 128 MB, Git LFS)
├── modules/
│   └── susfs4ksu-spes-vneid-v1.0.zip                                      ← module KSU cài ksu_susfs + dọn prop Lineage/userdebug + ẩn file Custom ROM + prop_watch + Action xoá cache VNeID
├── configs/
│   └── ksu-susfs.config                                                   ← fragment cấu hình KSU-Next + SuSFS
├── patches/
│   ├── 0001-spes-kernel-4.19-ksun-susfs-v1.5.5-selinux-cusrom-v8.patch    ← patch trên cây kernel spes (SuSFS 1.5.5 + manual hook + newfstat init.rc + SELinux hide + wildcard cusrom/maps + bỏ -Lineage)
│   └── 0002-ksunext-legacy-susfs-bridge-selinux-hide-setuid-v8.patch      ← patch trên KernelSU-Next legacy (susfs_bridge prctl+reboot + selinux_hide + bật TASK_STRUCT_NON_ROOT_USER_APP_PROC trong setuid_hook)
└── scripts/
    └── build.sh                                                           ← script dựng lại Image.gz từ upstream
```

---

## Các điểm vá trọng yếu trong Kernel `#8`

1. **Android 17 `init.rc` size hook (`fs/stat.c`):** `init` trên Android 17 dùng `fstat` (`newfstat` / `fstat64`) lấy `st_size` trước khi đọc `init.rc`, nên bổ sung `ksu_handle_newfstat_ret` / `ksu_handle_fstat64_ret` để `ksud services` và `boot-completed` luôn chạy đủ.
2. **SuSFS bridge 2 chiều (`KernelSU-Next/kernel/feature/susfs_bridge.c`):** hỗ trợ đồng thời `prctl(0xDEADBEEF)` cho CLI `ksu_susfs` v1.5.5 và `reboot(0xDEADBEEF, 0xFAFAFAFA)` cho giao diện KernelSU-Next Manager.
3. **Ẩn SELinux không side-channel (`security/selinux/ss/{policydb.h,services.c}` + `selinux_hide.c`):**
   - Đánh dấu `ksu_hidden` ngay trên `struct type_datum` cho type KSU và `adbroot`; chỉ chặn khi `uid >= 10000` (qua `security_context_to_sid`), trong khi `transive_to_domain()` nội bộ dùng `selinux_ksu_secctx_to_secid()` nên Manager & `su` chuyển sang `u:r:ksu:s0` bình thường.
   - Che `PROCESS__EXECMEM` trên `system_server -> system_server` và chặn `kernel -> adb_data_file` phát sinh từ `sepolicy.rule` của NeoZygisk.
4. **Sửa lỗi SuSFS bị vô hiệu khi không có module `/system` (`setuid_hook.c`):** đặt cờ `TASK_STRUCT_NON_ROOT_USER_APP_PROC` trực tiếp trong `ksu_handle_setresuid()` cho mọi app thường & isolated process thay vì phụ thuộc `ksu_module_mounted`.
5. **Wildcard ẩn Custom ROM + `/proc/self/{maps,smaps,map_files}` (`hooks.c`, `susfs.c`, `dcache.c`, `namei.c`, `readdir.c`, `task_mmu.c`, `base.c`):**
   - Port cơ chế `TASK_STRUCT_UNTRUSTED_APP` (`BIT(25)`) từ Mi 12S Pro: chỉ bật trong `selinux_setprocattr` khi domain là `u:r:untrusted_app*` hoặc `u:r:isolated_app*` (giữ nguyên cho `zygote` / `app_zygote` / `system_server` để không crash WebView/AppZygote).
   - Tự động ẩn mọi file `*lineage*`, `addon.d` trên phân vùng read-only, `*lineage*@idmap`, và ẩn khỏi `/proc/self/maps`, `/proc/self/smaps`, `/proc/self/smaps_rollup`, `/proc/self/map_files`.
6. **Xoá `-Lineage` nguyên bản khỏi `kernel/localversion`:** `uname -r`, `System.getProperty("os.version")` và `/proc/version` đồng nhất `4.19.325-cip137-st21` ngay từ lúc boot, không gây lỗi đỏ `Kernel release diverged` trên Duck Detector.

---

## Cài đặt nhanh trên máy `spes`

### 1. Flash boot image

> Nên sao lưu `boot_a` / `boot_b` gốc trước khi flash. Kiểm tra slot đang hoạt động bằng `fastboot getvar current-slot`.

```bash
fastboot flash boot_b kernel/boot_spes_ksun_susfs_v8.img
# (hoặc boot_a nếu máy đang chạy slot a)
fastboot reboot
```

### 2. Cài app & module Root
1. **KernelSU-Next Manager** bản CI UAPI v6 (`v3.4.2-292+`).
2. **NeoZygisk** (thay ZygiskNext).
3. **HMA-OSS** — chế độ Blacklist cho `com.vnid` (template ẩn `com.rifsxd.ksunext`, `org.frknkrc44.hma_oss` + preset `custom_rom`, `root_apps`, `sus_apps`, `xposed`, `detector_apps`, `accessibility_apps`, `shizuku_dhizuku`, settings preset `dev_options`).
4. **AlwaysStrong v1.0.6.1** (kèm `TEESimulator-RS v6.1.0-313` hỗ trợ Android 17 + per-instance VINTF): đặt `com.vnid!` và `com.eltavine.duckdetector!` (generate mode `!`) trong `/data/adb/tricky_store/target.txt` để khớp VINTF Keymaster `@4.1` (`41/4`) của `spes`.
5. **DuckUSB** (`../../modules/DuckUSB-Zygisk-2.2.0-no-adbd-contradiction.zip`): bật `frameworkMode`, `hookSystemServer`, `frameworkAllApps`, `spoofSettings`, `spoofProps`, `hideNotif`, `coverQueryPath`.
6. **SuSFS + VNeID Persist (`spes`)** (`modules/susfs4ksu-spes-vneid-v1.0.zip`): dọn sạch prop `ro.lineage.*` / `adb_root` / `userdebug` / `Lineage_spes`, ẩn `vendor_sepolicy.cil` / `file_contexts` / `debug.rc` + ghim inode + `prop_watch.sh` + nút Action xoá cache verdict VNeID.

---

## Tự dựng lại từ upstream

```bash
./scripts/build.sh
# Sau đó đóng gói Image.gz vào stock_boot.img của ROM bằng magiskboot:
magiskboot unpack stock_boot.img
cp spes-kernel-build/out/arch/arm64/boot/Image kernel
magiskboot repack stock_boot.img boot_spes_ksun_susfs_v8.img
```

---

## Trạng thái kiểm thử thực tế (26/11/2026)

- **VNeID (`com.vnid` v2.2.12):** **Hoạt động bình thường, hết sạch lỗi 05 và 012.**
- **Duck Detector:** `SELinux`, `Kernel Check`, `Bootloader`, `Mount`, `Play Integrity Fix`, `Zygisk` đều `[✔ CLEAR]`; `KeyMint VINTF` khớp `41/4` (TEE chỉ còn lệch manufacturer do keybox RKP Nubia của người dùng).
- **Cảnh báo:** Boot image chỉ dành riêng cho **Redmi Note 11 (`spes`)** chạy LineageOS 24 Android 17. Không flash lên máy khác.
