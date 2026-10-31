# Ẩn Root cho VNeID + App Ngân hàng — Xiaomi 12S Pro (unicorn) / LineageOS 24 (Android 17)

Bộ artifact + hướng dẫn để các app nhạy cảm (VNeID, HSBC, MB Bank) chạy ổn định trên máy đã
root KernelSU-Next + SuSFS, bền vững qua reboot.

- **Thiết bị:** Xiaomi 12S Pro (`unicorn`), SM8450/SM8475 (SD8+ Gen1)
- **ROM:** LineageOS 24 (Android 17), SDK 37, `arm64-v8a`
- **Root:** KernelSU-Next v3.4.2 (`ksud 3.4.2`, uapi 5) + SuSFS v2.3.0
- **Kernel tuỳ biến:** `5.10.269-gki`, build `#7`, SuSFS wildcard patch v3

---

## 0. Nội dung thư mục

```
android-root-bundle/
├── README.md                        ← file này
├── kernel/
│   ├── boot_ksun_susfs_v5.img       ← boot image đã build (flash thẳng hoặc fastboot boot test)
│   │                                  SHA256: afccf86ce48f36f483d32863355726f89a847125b4be6f1ecd99e0eeb09c72db
│   └── AnyKernel3-unicorn-ksun-susfs-v3.zip  ← bản zip flash qua recovery/KSU (cùng kernel)
├── modules/
│   ├── lineage_charge_guard-v1.0.zip   ← Fix lỗi treo boot do race-condition node sạc của LineageOS
│   └── vneid_persist-v2.2.zip            ← module tự viết: dọn prop + nạp sus_path (chỉ có ở repo này)
├── patches/
│   ├── 0001-unicorn-integrate-KernelSU-Next-v3.4.2-SuSFS-v2.3.0-.patch  ← ghép KSU-Next + SuSFS
│   ├── 0002-susfs-wildcard-cusrom-untrusted-app.patch                   ← patch wildcard ẩn ROM (v3)
│   └── KERNEL_PATCH_REVIEW.md            ← review hard của patch wildcard
└── SHA256SUMS                       ← hash verify toàn bộ artifact
```

### Tự build lại kernel (tuỳ chọn)

File `boot_ksun_susfs_v5.img` trong repo dùng được luôn. Muốn tự build (ví dụ để kiểm chứng,
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
| resetprop-rs (tích hợp sẵn trong `vneid_persist` v2.2) | Xoá prop không dấu vết (`--nuke`) + ngủ chờ futex (`--wait`) | https://github.com/Enginex0/resetprop-rs/releases | v0.6.0 |
| Mountify | Meta-module mount | https://github.com/backslashxx/mountify/releases | — |


---

## 1. Cần những module gì (toàn cảnh stack)

Thứ tự lớp phòng thủ của app và module trị từng lớp:

| Lớp app kiểm tra | Module/giải pháp | Ghi chú |
|---|---|---|
| Play Integrity + Key Attestation (keybox) | **AlwaysStrong** (Tricky Store + TEESimulator) | per-app target list |
| File ROM/su, `/proc/self/maps` | **Kernel SuSFS wildcard v3** + **vneid_persist** | `boot_ksun_susfs_v5.img` + module |
| Ẩn mount, spoof uname, cấp `ksu_susfs` | **BRENE** | bật, tắt toàn bộ tab ROM |
| Danh sách app / accessibility | **HMA-OSS** (Zygisk) | VNeID + bank chạy **Blacklist** |
| **Dấu vết injector Zygisk** (`zygisk_atexit_soinfo`) | **NeoZygisk v2.4** | **thay BreZygisk** — mấu chốt cho MB Bank |
| Prop `ro.lineage.*`, `adb_root` | **vneid_persist** (service.sh) | dọn mỗi lần boot |

Danh sách module đang BẬT trên máy (tham chiếu):
`brene`, `hma_oss_zygisk`, `mountify`, `tricky_store` (AlwaysStrong), `vneid_persist`,
và `zygisksu` (**NeoZygisk** — thay `rezygisk` đã disable).

---

## 2. Cài từ đầu (máy sạch, hoặc dựng lại)

> **Nguyên tắc an toàn:** luôn `fastboot boot` chạy RAM để test TRƯỚC khi flash cố định.

### Bước 1 — Kernel SuSFS wildcard
```
# Test (không ghi đĩa): vào fastboot rồi
fastboot boot kernel/boot_ksun_susfs_v5.img
# → vào hệ thống, mở VNeID kiểm tra OK, rồi mới flash cố định:
fastboot flash boot_a kernel/boot_ksun_susfs_v5.img
fastboot flash boot_b kernel/boot_ksun_susfs_v5.img
```
(Hoặc flash `AnyKernel3-unicorn-ksun-susfs-v3.zip` qua KSU/recovery nếu đang chạy được.)

### Bước 2 — Root modules cơ bản (qua KernelSU Manager)
Cài theo thứ tự, reboot sau mỗi nhóm nếu manager yêu cầu:
1. **BRENE** — bật, vào app TẮT toàn bộ tab ROM (`=0`).
2. **NeoZygisk** (tải từ https://github.com/JingMatrix/NeoZygisk/releases, bản đã test v2.4-289) — injector Zygisk.
   - Nếu máy đang có BreZygisk/ReZygisk: `touch /data/adb/modules/rezygisk/disable` trước, rồi cài NeoZygisk, reboot.
3. **HMA-OSS** — module Zygisk ẩn app list.
4. **AlwaysStrong** (https://gitlab.com/Evokerr/AlwaysStrong/-/releases) — gồm Tricky Store + TEESimulator, keybox attestation.
5. **vneid_persist** (`modules/vneid_persist-v2.2.zip`) — dọn prop + sus_path.

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
- **NeoZygisk → BreZygisk:** xóa `/data/adb/modules/zygisksu`, gỡ `disable` của `rezygisk`, reboot.
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
