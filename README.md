# Ẩn Root cho VNeID + App Ngân hàng — Xiaomi 12S Pro (unicorn) / LineageOS 24 (Android 17)

Bộ artifact + hướng dẫn để các app nhạy cảm (VNeID, HSBC, MB Bank) chạy ổn định trên máy đã
root KernelSU-Next + SuSFS, bền vững qua reboot.

- **Thiết bị:** Xiaomi 12S Pro (`unicorn`), SM8450/SM8475 (SD8+ Gen1)
- **ROM:** LineageOS 24 (Android 17), SDK 37, `arm64-v8a`
- **Root:** KernelSU-Next v3.4.2 (`ksud 3.4.2`, uapi 5) + SuSFS v2.3.0
- **Kernel tuỳ biến:** `5.10.269-gki`, build `#23` (Kernel v7: ZeroMount VFS + SuSFS Enhanced + SELinux Timing Fix + In-kernel Quirks)

---

## 0. Nội dung thư mục

```
android-root-bundle/
├── README.md                        ← file này
├── kernel/
│   ├── boot_ksun_susfs_v7.img       ← boot image Kernel v7 (#23) fix KSU SELinux context timing + ZeroMount VFS + SuSFS Enhanced
│   └── AnyKernel3-unicorn-ksun-susfs-v7.zip  ← bản zip flash qua recovery/KSU (Kernel v7)
├── modules/
│   ├── vneid_persist-v2.5.zip       ← dọn prop, nạp sus_path/map/loop (an toàn cho AppZygote) + bảo vệ 9 file sepolicy/file_contexts qua open_redirect + Action xoá cache verdict cũ của VNeID
│   ├── DuckUSB-Zygisk-2.2.0-no-adbd-contradiction.zip ← bản DuckUSB 2.2.0 đã vá service.sh (bỏ spoof init.svc.adbd=stopped, tránh lỗi đỏ ADB Runtime contradiction trên Duck Detector; vẫn ẩn USB debugging & giữ System Properties xanh)
│   ├── hide-developer-options-1.1.1-boot-safe.zip ← giữ Dev options/USB debugging BẬT qua reboot mà không bị Duck Detector warning Mount; tắt tạm khi mở app trong packages.txt
│   └── lineage_charge_guard-v1.0.zip ← (Đã lỗi thời từ Kernel v5: kernel đã tự tích hợp quirk sạc, không cần cài)
├── patches/
│   ├── 0001-unicorn-integrate-KernelSU-Next-v3.4.2-SuSFS-v2.3.0-.patch  ← ghép KSU-Next + SuSFS
│   ├── 0002-susfs-wildcard-cusrom-untrusted-app.patch                   ← patch wildcard ẩn ROM (v3)
│   └── KERNEL_PATCH_REVIEW.md            ← review hard của patch wildcard
└── SHA256SUMS                       ← hash verify toàn bộ artifact
```

### Tự build lại kernel (tuỳ chọn)

File `boot_ksun_susfs_v7.img` trong repo dùng được luôn. Muốn tự build (ví dụ để kiểm chứng,
hoặc khi LineageOS đổi kernel) thì làm như sau trên Linux x86_64:

1. **Lấy source kernel LineageOS cho unicorn**, đúng commit mà ROM stock đang chạy
   (`uname -r` trên máy ra `5.10.269-gki-geff4b40407a1`, tức commit `eff4b4040`):
   ```
   git clone https://github.com/LineageOS/android_kernel_xiaomi_sm8450 kernel
   cd kernel && git checkout eff4b4040
   ```
2. **Áp 2 patch trong thư mục `patches/`** theo thứ tự:
   ```
   git am ../patches/0001-unicorn-integrate-KernelSU-Next-v3.4.2-SuSFS-v2.3.0-.patch
   git apply ../patches/0002-susfs-wildcard-cusrom-untrusted-app.patch
   ```
   - `0001`: ghép KernelSU-Next v3.4.2 + SuSFS v2.3.0
   - `0002`: patch wildcard của SuSFS để ẩn file ROM (`*lineage*`) khỏi app người dùng
3. **Toolchain:** AOSP clang `r596125` (prebuilt Clang của Android, tải từ
   `android.googlesource.com/platform/prebuilts/clang/host/linux-x86`), cho vào `PATH`.
4. **Build `Image`** (GKI defconfig + các fragment vendor của unicorn):
   ```
   M="make O=out ARCH=arm64 LLVM=1 LLVM_IAS=1 CC=clang TARGET_PRODUCT=unicorn"
   $M gki_defconfig
   scripts/kconfig/merge_config.sh -m -O out out/.config \
     arch/arm64/configs/vendor/waipio_GKI.config \
     arch/arm64/configs/vendor/xiaomi_GKI.config \
     arch/arm64/configs/vendor/unicorn_GKI.config \
     arch/arm64/configs/vendor/debugfs.config
   $M olddefconfig
   $M -j$(nproc) Image
   ```
5. **Đóng gói vào boot.img:** lấy `boot.img` stock trích từ ROM LineageOS, rồi chỉ thay mỗi kernel
   bằng `magiskboot`:
   ```
   magiskboot unpack boot.img
   cp out/arch/arm64/boot/Image kernel
   magiskboot repack boot.img boot_new.img
   ```
6. **Kiểm tra ABI trước khi flash:** so `vmlinux.symvers` của bản build có patch với bản build
   không patch (cùng commit) — phải ra **0 dòng khác** thì các module vendor (`.ko` trong
   `vendor_dlkm`: Wi-Fi, camera, DSP...) mới nạp được. Lệch ABI là máy mất Wi-Fi/camera hoặc
   không boot.

> Luôn `fastboot boot boot_new.img` để chạy thử trên RAM trước khi flash cố định.

---

### Module bên thứ ba (dùng nguyên bản — tải từ nguồn chính thức)

Repo này chỉ chứa những thứ **đã tự sửa/tự viết** (kernel, patch, `vneid_persist`). Các module dưới
đây dùng nguyên bản, tải bản release mới nhất từ trang gốc:

| Module | Vai trò | Nguồn | Bản đã test |
|---|---|---|---|
| KernelSU-Next (manager) | Root, quản lý module | https://github.com/KernelSU-Next/KernelSU-Next/releases | v3.4.2 |
| SuSFS (tham khảo, đã ghép vào kernel) | Ẩn path/mount/maps ở kernel | https://gitlab.com/simonpunk/susfs4ksu | v2.3.0 |
| **NeoZygisk** | Injector Zygisk, che dấu `atexit` | https://github.com/JingMatrix/NeoZygisk/releases | v2.4 (289) |
| BRENE | Cấp `ksu_susfs`, ẩn mount, spoof uname | https://github.com/rrr333nnn333/BRENE/releases | — |
| HMA-OSS (Hide My Applist) | Ẩn danh sách app (cần Zygisk) | https://github.com/frknkrc44/HMA-OSS/releases | — |
| **AlwaysStrong** (gồm Tricky Store + TEESimulator) | Keybox / key attestation, giả lập TEE theo từng app | https://gitlab.com/Evokerr/AlwaysStrong/-/releases | v1.0.5 |
| resetprop-rs (tích hợp sẵn trong `vneid_persist` v2.3) | Xoá prop không dấu vết (`--nuke`) + ngủ chờ futex (`--wait`) | https://github.com/Enginex0/resetprop-rs/releases | v0.6.0 |
| **ZeroMount** (`meta-zeromount`) | Meta-module VFS mountless (thay thế Mountify/MagicMount) | https://github.com/Enginex0/zeromount/releases | v2.0.216-dev |


---

## 1. Cần những module gì (toàn cảnh stack)

Thứ tự lớp phòng thủ của app và module trị từng lớp:

| Lớp app kiểm tra | Module/giải pháp | Ghi chú |
|---|---|---|
| Play Integrity + Key Attestation (keybox) | **AlwaysStrong** (Tricky Store + TEESimulator) | per-app target list |
| File ROM/su, `/proc/self/maps` | **Kernel SuSFS wildcard v3** + **vneid_persist** | `boot_ksun_susfs_v7.img` + module |
| Ẩn mount, spoof uname, cấp `ksu_susfs` | **BRENE** | bật, tắt toàn bộ tab ROM |
| Danh sách app / accessibility | **HMA-OSS** (Zygisk) | VNeID + bank chạy **Blacklist** |
| **Dấu vết injector Zygisk** (`zygisk_atexit_soinfo`) | **NeoZygisk v2.4** | **thay BreZygisk** — mấu chốt cho MB Bank |
| Prop `ro.lineage.*`, `adb_root` | **vneid_persist** (service.sh) | dọn mỗi lần boot |

Danh sách module đang BẬT trên máy (tham chiếu):
`brene`, `hma_oss_zygisk`, `meta-zeromount` (ZeroMount VFS), `ohmyfont`, `tricky_store` (AlwaysStrong), `vneid_persist` (v2.3),
và `zygisksu` (**NeoZygisk** v2.4).

---

## 2. Cài từ đầu (máy sạch, hoặc dựng lại)

> **Nguyên tắc an toàn:** luôn `fastboot boot` chạy RAM để test TRƯỚC khi flash cố định.

### Bước 1 — Kernel SuSFS wildcard
```
# Test (không ghi đĩa): vào fastboot rồi
fastboot boot kernel/boot_ksun_susfs_v7.img
# → vào hệ thống, mở VNeID kiểm tra OK, rồi mới flash cố định:
fastboot flash boot_a kernel/boot_ksun_susfs_v7.img
fastboot flash boot_b kernel/boot_ksun_susfs_v7.img
```
(Hoặc flash `AnyKernel3-unicorn-ksun-susfs-v3.zip` qua KSU/recovery nếu đang chạy được.)

### Bước 2 — Root modules cơ bản (qua KernelSU Manager)
Cài theo thứ tự, reboot sau mỗi nhóm nếu manager yêu cầu:
1. **BRENE** — bật, cung cấp `ksu_susfs`, ẩn mount.
2. **NeoZygisk** (v2.4-289) — injector Zygisk độc lập, che giấu hoàn toàn destructor `__cxa_atexit`.
3. **HMA-OSS** — module Zygisk ẩn app list (Blacklist cho VNeID + Bank).
4. **AlwaysStrong** — gồm Tricky Store + TEESimulator, xử lý Keybox attestation.
5. **vneid_persist** (`modules/vneid_persist-v2.6.zip`) — dọn prop, nạp sus_path/map/loop (bảo toàn 3 APK hệ thống cho AppZygote) và tự động thiết lập `open_redirect` cho 9 file sepolicy/file_contexts/Updater.xml.
   - **Action (v2.6):** KernelSU Manager → Module → vneid_persist → nút Action = dừng VNeID, xoá 2 file verdict BShield (`cmwoawp.ogg`, `xwoccmwldwasxm.dat`) + `cache/*` + `app_webview/*`; giữ `SKS_*` (đăng nhập/sinh trắc). Dùng khi VNeID còn báo mã lỗi cũ; mở lại app để BShield kiểm tra lại (file tự sinh lại).
6. **ZeroMount** (`meta-zeromount`) — metamodule nạp module qua VFS redirection (dùng nạp `ohmyfont` không để lại mount point).

7. **Hide Developer Options** (`modules/hide-developer-options-1.1.1-boot-safe.zip`, sửa từ jksalcedo 1.0) — chỉ cần nếu muốn để Dev options + USB debugging bật.
   - Vì sao: bật Dev options + USB debugging lúc tắt máy ⇒ `persist.sys.usb.config=adb` khiến adbd chạy trước zygote ⇒ process isolated lệch mount namespace ⇒ Duck Detector Mount "Cross-process mount views: 2 view(s)". BRENE (`config_developer_options=0`) tắt options ở boot-completed nhưng đã muộn.
   - Module: `post-fs-data` bỏ `adb` khỏi `persist.sys.usb.config` + đặt 3 setting về 0 trong `settings_global.xml` (backup `settings_global.bak`), để trống 3 key dev/usb/wireless của BRENE; ~30 s sau boot bật lại theo `desired.state`.
   - Cài lần đầu: bật Dev options/USB debugging tay một lần (hoặc ghi sẵn `/data/adb/hide_developer_options/desired.state`). Thêm `com.eltavine.duckdetector` (và app cần che) vào `/data/adb/hide_developer_options/packages.txt` để hết warning ADB Runtime / System Properties khi quét. Log: `/data/adb/hide_developer_options/log.txt`.

### Bước 3 — Reboot, kiểm tra
Mở VNeID, HSBC, MB Bank. Nếu lỗi, xem mục 4 (Trị theo từng app).

---

## 3. Vì sao cần NeoZygisk (thay BreZygisk)

MB Bank (`com.mbmobile`, Zimperium zDefend v12) có rule **`zygisk_atexit_soinfo`** phát hiện
chính injector Zygisk: module Zygisk đăng ký destructor qua `__cxa_atexit` → để lại dấu trong
`AtexitArray g_array` của libc; khi injector tự unmap thì lộ handler treo/gap → Zimperium bắt được.

- `sus_path`/keybox/HMA **vô dụng** ở đây vì dấu vết nằm trong RAM tiến trình, không phải file.
- **NeoZygisk** tự cài `__cxa_atexit` riêng, chặn mọi đăng ký của injector → không để lại dấu.
- BreZygisk/ReZygisk có ẩn `solist` nhưng vẫn lộ `atexit` dưới rule v12.
- NeoZygisk v2.4 còn thêm chữ ký app-specialize cho **Android 17** (BreZygisk v1.0.0 không có).

NeoZygisk nạp lại y nguyên các Zygisk module cũ (`tricky_store`, `hma_oss_zygisk`) — không cần cấu hình lại. Kernel SuSFS không bị đụng.

---

## 4. Trị theo từng app (checklist Zimperium)

### VNeID (`com.vnid`) — CA-E012 custom-ROM
- Cần: kernel SuSFS wildcard v3 + `vneid_persist` (nạp `add_sus_path_loop` các path `*lineage*`
  + 5 file `*debug*.rc`). Kernel v3 tự re-flag `path+map` mỗi lần Zygote fork app → miễn nhiễm
  `icache` eviction, không cần cron.
- HMA: để **Blacklist**, preset `[custom_rom, root_apps, sus_apps, xposed]`.

### VNeID lỗi 12 sau nhiều giờ uptime (prop tái sinh)
`LineageSettingsService` tự tạo lại `sys.lineage_settings_system_version` lúc runtime (dọn lúc boot
vẫn quay lại sau vài giờ) → VNeID lỗi 12. File `*lineage*@idmap` lúc đó vẫn ẩn tốt (ENOENT).
Fix (v2.2): tích hợp `resetprop-rs` (`bin/resetprop-rs`) vào `vneid_persist`:
- Dùng `--nuke` thay cho `resetprop -d`: xóa prop nhưng giữ nguyên tổng số lượng prop, điền tên giả hợp lệ và dồn mảnh bộ nhớ `/dev/__properties__/` (chống quét pháp y `Prop area anomalies`).
- `prop_watch.sh` dùng `resetprop-rs --wait` ngủ đông trên kernel futex (`futex_wait_queue_me`, **0% CPU, 0 polling**) cho cả 3 prop `sys.lineage_settings_{system,secure,global}_version` — thức dậy và `--nuke` ngay sau ~15ms khi prop vừa sinh ra (khép hoàn toàn cửa sổ hở 60s cũ).
- Kiểm tra: `pgrep -af "resetprop-rs --wait"` (3 waiter đang ngủ futex), log ở `last.log`.

### HSBC (`vn.hsbc.hsbcvietnam`) — Zimperium `android_serial_banning`
- **GỠ** khỏi `/data/adb/tricky_store/target.txt`; khóa `vn.hsbc.hsbcvietnam	off` trong
  `/data/adb/tricky_store/alwaysstrong/apps.map` (để TEESimulator không tiêm keybox công khai
  mà dùng TEE cert thật của máy).

### MB Bank (`com.mbmobile`) — Zimperium nhiều rule
Đã xử lý trọn gói:
1. `android_serial_banning` → **gỡ** khỏi `target.txt`, khóa `off` trong `apps.map`.
2. `android_custom_rom` → HMA Blacklist, preset giống VNeID (thêm `sus_apps`).
3. `userdebug_detection` → ẩn 5 file `*debug*.rc` / `gps_debug.conf` (vneid_persist lo sẵn).
4. **`zygisk_atexit_soinfo` → NeoZygisk** (điểm mấu chốt).
- Lưu ý: các chuỗi `zygisk_atexit_soinfo`/`jailbroken`/`rooted` vẫn còn trong RAM là **định nghĩa
  rule catalog** Zimperium tải về (có trên mọi máy kể cả không root). Tín hiệu thật là app
  **tự thoát / không hiện màn chính**, không phải grep hits.

---

## 5. Rollback

- **Kernel:** `fastboot flash boot_a <boot cũ>` / flash lại stock `boot.img`.
- **NeoZygisk:** nếu cần gỡ, chỉ cần xóa thư mục `/data/adb/modules/zygisksu` và reboot.
- **vneid_persist:** xóa `/data/adb/modules/vneid_persist`, reboot.

---

## 6. OTA LineageOS — QUAN TRỌNG
Auto-OTA đã **tắt 3 lớp** (`org.lineageos.updater` disabled-user, `ota_disable_automatic_update=1`,
`auto_updates_check_interval=0`). OTA sẽ ghi đè `boot.img` → mất KernelSU+SuSFS+wildcard. Khi muốn
update: làm **manual**, và nếu commit kernel đổi thì **build lại kernel** theo mục *Tự build lại kernel* ở trên (đổi sang commit kernel mới của LineageOS, áp lại 2 patch)
(coi chừng lệch ABI `.ko`).

---

_Ghi chú build: boot v3 SHA256 `afccf86ce48f36f483d32863355726f89a847125b4be6f1ecd99e0eeb09c72db`,
ABI diff vs base = 0 dòng, kernel `#7 SMP PREEMPT`._

---

## 7. Hardening nâng cao (giảm dấu vết với app dò root, vd Duck Detector)

Sau khi stack cơ bản chạy ổn, bật thêm các mục dưới để giảm fingerprint custom-ROM mà
app ngân hàng đời mới có thể quét. Kiểm chứng bằng app **Duck Detector** (`com.eltavine.duckdetector`):
export báo cáo ra `/sdcard/Download/`, đối chiếu trước/sau.

### 7.1 Bật 2 toggle BRENE (ẩn chuỗi LineageOS ở tầng file)
Trong `/data/adb/brene/config.sh`:
```
config_hide_lineage_strings=1      # redirect *sepolicy.cil, *file_contexts, *.rc chứa "lineage", Updater.xml → file rỗng
config_spoof_libstagefright=1      # redirect /system/lib64/libstagefright.so → file rỗng
```
BRENE dùng `ksu_susfs add_open_redirect <target> <fake> 3` (scheme 3 = chỉ áp cho app bị
umount, uid≥10000 = chính các app bank), nên **không ảnh hưởng hệ thống** → rủi ro bootloop thấp.
Cần reboot. Trị được các finding: `nativePolicy *file_contexts hits`, `libstagefright symbol`.

### 7.2 Ẩn thư mục rác trên sdcard của app đã bị HMA giấu
Vấn đề: HMA ẩn app khỏi PackageManager, nhưng `/sdcard/Android/data/<pkg>` vẫn còn →
app dò thấy qua FUSE stat và báo "HMA concealment detected" (đỏ). Fix: bật toggle BRENE
```
config_hide_ksu_directories=1
```
rồi thêm package cần xóa vào `/data/adb/modules/brene/remove_ksu_directory.sh`:
```
remove_directory "org.frknkrc44.hma_oss"   # HMA-OSS
remove_directory "<ksu-manager-package>"   # app KernelSU (kể cả khi đã đổi tên)
```
BRENE xóa các thư mục này lúc boot + đặt `inotifyd` tự xóa lại khi chúng tái xuất hiện.
Chạy sau `boot_completed` nên không gây bootloop.
> Lưu ý: file `remove_ksu_directory.sh` thuộc BRENE → **sửa lại sau mỗi lần update BRENE**.

### 7.3 Đồng bộ HMA Blacklist cho mọi app nhạy cảm
Trong `/data/misc/hide_my_applist_*/config.json`, mỗi app bank/VNeID nên dùng CÙNG template
blacklist (`black vneid`) + CÙNG presets `["custom_rom","root_apps","sus_apps","xposed"]`.
Template blacklist phải chứa ít nhất: app KernelSU manager, `org.frknkrc44.hma_oss`,
`com.termux`, và mọi module LSPosed (vd `balti.xposed.pixelifygooglephotos`). Diff block config
của app đang chạy tốt với app mới trước khi sửa.

### 7.4 Những thứ KHÔNG ẩn được bằng module (giới hạn cứng)
- **KHÔNG bật `Hide third party apps` (`config_hide_third_party_apps=0`) trong BRENE v0.0.73+**: lệnh `set_priority_uid_filter` của nó gây treo/tự reboot trên kernel hiện tại (đã test thực tế).
- **11 service `lineage*` trong ServiceManager** (`lineagehardware`, `lineagehealth`,
  `vendor.lineage.*`...): mọi app gọi `listServices` đều thấy; chỉ hết khi đổi ROM.
- **Mount / SELinux "paradox" warning**: heuristic mềm, `/proc/self/mounts` sạch, không phải tell root.
- **Network Risk**: do đang bật VPN (Tailscale/WARP), không liên quan root.

Các lớp attestation thật mà bank dựa vào (TEE/key attestation, bootloader locked+verified,
Zygisk, native root, props) đều PASS với stack này — đó mới là phần quyết định.

### Module bổ trợ sửa lỗi riêng của ROM LineageOS

#### `lineage_charge_guard-v1.0.zip` (Tùy chọn cho LineageOS)
- **Mục đích:** Sửa dứt điểm lỗi thiết kế (race condition) của chính ROM **LineageOS** trên Xiaomi 12S Pro (`unicorn`).
- **Nguyên nhân kỹ thuật:** LineageOS chạy service `vendor.lineage.health-service.default` dưới quyền user `system` (UID 1000) và dùng vòng lặp vô tận `while (!mChargingEnabledNode)` đòi quyền ghi (`W_OK`) vào node sạc `/sys/class/qcom-battery/input_suspend` (mặc định của kernel là `0644 root:root`). Nếu `ueventd` bị chậm hoặc bận nạp firmware Wi-Fi/Modem, file không kịp chown sang `system:system 0660`, service này sẽ kẹt vĩnh viễn khiến `system_server` bị Android Watchdog giết và kẹt ở màn hình khởi động (quay logo).
- **Cơ chế fix:** Chạy nền ở giai đoạn `post-fs-data.sh`, thăm dò mỗi 100ms và tự động cấp quyền `0660 system:system` ngay trong mili-giây đầu tiên node sạc vừa xuất hiện.
- **Lưu ý:** Chỉ cần dùng khi chạy ROM LineageOS (hoặc các ROM fork từ Lineage). Nếu sau này chuyển sang ROM thuần AOSP hoặc HyperOS, chỉ cần gỡ bỏ module này mà không ảnh hưởng gì tới các module khác.

### Kernel v5 (Tích hợp trực tiếp LineageOS Charging Node Quirk vào Kernel)
- **Điểm mới:** Bổ sung quirk trực tiếp tại `fs/kernfs/file.c (__kernfs_create_file)` cấp quyền `R_OK | W_OK` cho user `system` (UID 1000) trên node `/sys/class/qcom-battery/input_suspend` ngay khi node được tạo ra.
- **Lợi ích:** Triệt tiêu hoàn toàn race condition gây treo boot của ROM LineageOS mà **không cần cài module `lineage_charge_guard` nữa** (có thể gỡ bỏ module này để máy sạch gọn 100%).

### Kernel v6 (ZeroMount VFS Driver + Enhanced SuSFS Kstat Redirect + Process-Context Supercall)
- **ZeroMount VFS (`CONFIG_ZEROMOUNT=y`, `/dev/zeromount`):** Chuyển hướng đường dẫn file ở tầng VFS (`getname`, `d_path`, `readdir`, `statx`, `statfs`, `xattr`, `/proc/PID/maps`) với 0 mount point trong `/proc/mounts`.
- **Enhanced SuSFS (`CONFIG_KSU_SUSFS_SUS_KSTAT_REDIRECT=y`, `0x55573`):** Hỗ trợ dual-inode kstat redirect cho ZeroMount (`susfs_mode: enhanced`).
- **Process-Context Supercall (`kernel/reboot.c`):** Chuyển `SUSFS_MAGIC` (`0xFAFAFAFA`) ra khỏi atomic kprobe `reboot_handler_pre` sang `SYSCALL_DEFINE4(reboot)` giúp `SYS_reboot` trả về `0` chuẩn xác và triệt tiêu lỗi sleeping-in-atomic khi cập nhật `open_redirect`.
- **SELinux Hide (`selinux_hide.c`):** Ẩn trace userdebug của LineageOS (`adbroot`, `shell -> su`) và tối ưu `security_context_to_sid_with_policy` (stack buffer + chỉ parse `backup_sepolicy` trước khi chạm `orig_policy`) để khử bất đối xứng timing `app_zygote` `attr/current` (A−B ≤ 0 ns).
- **SELinux KSU Context Timing Parity (`selinux_hide.c`, build `#21`):** Chuẩn hoá đường đi quét chuỗi và hash lookup của `"ksu"`/`"ksu_file"`/`"adbroot"` trong `string_to_context_struct_single` theo `"duck_detector_invalid"` (21 ký tự, bucket `3482`), triệt tiêu độ lệch `-173 ns` của probe `ksu_types timing with invalid types` (raw selinuxfs write & `setprocattr` trên CPU 0 Cortex-A510).
- **Android 17 `netlink_xperm` -> `nlmsg_readpriv`/`nlmsg_getneigh` (`security/selinux/ss/policydb.c`, build `#21`):** Ánh xạ policy capability bit 9 (`netlink_xperm` của `secilc` Android 17) sang `p->android_netlink_route = 1` và `p->android_netlink_getneigh = 1` trong `policydb_read()` và bảo toàn 2 cờ `POLICYDB_CONFIG_ANDROID_NETLINK_*` trong `policydb_write()`, chặn đứng `AF_NETLINK MAC Leak` (`RTM_GETLINK`) và `AF_NETLINK Neighbor Leak` (`RTM_GETNEIGH`) từ `untrusted_app`.

### Kernel v7 (Fix SELinux KSU Context Timing trên Duck Detector Build 1124+, build `#23`)
- **Nguyên nhân từ v6 (`#21`):** Bản Duck Detector mới hơn so sánh cặp chuỗi cùng độ dài 3 ký tự (`u:r:ksu:s0` vs `u:r:inv:s0`). Vòng lặp `ksu_timing_pad` 21 ký tự (`"duck_detector_invalid"`) trong `string_to_context_struct_single()` của v6 khiến `"ksu"` chậm hơn `"inv"` khoảng **+104 ns** (~2 tick ARM64 `cntvct_el0`) trên cả `/sys/fs/selinux/context` lẫn `setprocattr` (`/proc/self/attr/current`).
- **Fix (`drivers/kernelsu/feature/selinux_hide.c`):** Bỏ `"ksu"`, `"ksu_file"` (vốn đã không tồn tại trong `backup_sepolicy` trước khi KernelSU nạp rule) và xoá vòng lặp `ksu_timing_pad`, chỉ giữ lại chặn `"adbroot"`. Cả `"ksu"` và `"inv"` nay đi chung đúng 1 nhánh `symtab_search()` 3 byte trên `backup_sepolicy`, triệt tiêu hoàn toàn cảnh báo đỏ `Enforcing with KSU context timing anomaly` (đã test thực tế trên Mi 12S Pro + ABI `vmlinux.symvers` diff 0 dòng).

### Module `DuckUSB-Zygisk-2.2.0-no-adbd-contradiction.zip`
- **Nguồn gốc:** Vá từ `DuckUSB-Zygisk-2.2.0-release.zip` (cập nhật lại SHA256 trong `customize.d/00-verify-resources.sh` để cài đặt chuẩn qua KSU/Magisk).
- **Vấn đề bản gốc:** `service.sh` ép `resetprop -n init.svc.adbd stopped` trong khi tiến trình `adbd` vẫn đang chạy thật → mâu thuẫn với `/dev/socket/adbd` và abstract socket `@jdwp-control` khiến Duck Detector nâng từ Warning vàng lên **Danger đỏ** (`ADB Runtime: 2 runtime contradiction(s)`).
- **Bản vá:** Bỏ `init.svc.adbd=stopped` khỏi `LIST` (chỉ giữ mask `persist.sys.usb.config=mtp` và `sys.usb.state=mtp`, đổi `WAIT_KEY` sang `sys.usb.state`). Kết quả: `System Properties` vẫn xanh, mọi app vẫn đọc `adb_enabled=0` / `development_settings_enabled=0`, và hết hoàn toàn lỗi đỏ `ADB Runtime` contradiction.
