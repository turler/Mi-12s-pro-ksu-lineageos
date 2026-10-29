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
│   ├── boot_ksun_susfs_v3.img       ← boot image đã build (flash thẳng hoặc fastboot boot test)
│   │                                  SHA256: afccf86ce48f36f483d32863355726f89a847125b4be6f1ecd99e0eeb09c72db
│   └── AnyKernel3-unicorn-ksun-susfs-v3.zip  ← bản zip flash qua recovery/KSU (cùng kernel)
├── modules/
│   ├── NeoZygisk-v2.4-289-release.zip    ← injector Zygisk (thay BreZygisk) — trị MB Bank
│   └── vneid_persist-v2.0.zip            ← module dọn prop + nạp sus_path lúc boot
└── patches/
    ├── 0001-unicorn-integrate-KernelSU-Next-v3.4.2-SuSFS-v2.3.0-.patch  ← ghép KSU-Next + SuSFS
    ├── 0002-susfs-wildcard-cusrom-untrusted-app.patch                   ← patch wildcard ẩn ROM (v3)
    └── KERNEL_PATCH_REVIEW.md            ← review hard của patch wildcard
SHA256SUMS                           ← hash verify toàn bộ artifact
```

> Mã nguồn kernel đã patch nằm ở `~/kbuild/kernel` trên cùng máy WSL này. Build lại bằng
> `~/kbuild/build.sh` (xem REPORT.md / BRIEF.md trong `~/kbuild`).

---

## 1. Cần những module gì (toàn cảnh stack)

Thứ tự lớp phòng thủ của app và module trị từng lớp:

| Lớp app kiểm tra | Module/giải pháp | Ghi chú |
|---|---|---|
| Play Integrity + Key Attestation (keybox) | **Tricky Store** (AlwaysStrong) | per-app target list |
| File ROM/su, `/proc/self/maps` | **Kernel SuSFS wildcard v3** + **vneid_persist** | `boot_ksun_susfs_v3.img` + module |
| Ẩn mount, spoof uname, cấp `ksu_susfs` | **BRENE** | bật, tắt toàn bộ tab ROM |
| Danh sách app / accessibility | **HMA-OSS** (Zygisk) | VNeID + bank chạy **Blacklist** |
| **Dấu vết injector Zygisk** (`zygisk_atexit_soinfo`) | **NeoZygisk v2.4** | **thay BreZygisk** — mấu chốt cho MB Bank |
| Prop `ro.lineage.*`, `adb_root` | **vneid_persist** (service.sh) | dọn mỗi lần boot |

Danh sách module đang BẬT trên máy (tham chiếu):
`brene`, `hma_oss_zygisk`, `mountify`, `ohmyfont`, `tricky_store`, `vneid_persist`,
`zygisk_vector` (LSPosed Vector), và `zygisksu` (**NeoZygisk** — thay `rezygisk` đã disable).

---

## 2. Cài từ đầu (máy sạch, hoặc dựng lại)

> **Nguyên tắc an toàn:** luôn `fastboot boot` chạy RAM để test TRƯỚC khi flash cố định.

### Bước 1 — Kernel SuSFS wildcard
```
# Test (không ghi đĩa): vào fastboot rồi
fastboot boot kernel/boot_ksun_susfs_v3.img
# → vào hệ thống, mở VNeID kiểm tra OK, rồi mới flash cố định:
fastboot flash boot_a kernel/boot_ksun_susfs_v3.img
fastboot flash boot_b kernel/boot_ksun_susfs_v3.img
```
(Hoặc flash `AnyKernel3-unicorn-ksun-susfs-v3.zip` qua KSU/recovery nếu đang chạy được.)

### Bước 2 — Root modules cơ bản (qua KernelSU Manager)
Cài theo thứ tự, reboot sau mỗi nhóm nếu manager yêu cầu:
1. **BRENE** — bật, vào app TẮT toàn bộ tab ROM (`=0`).
2. **NeoZygisk** (`modules/NeoZygisk-v2.4-289-release.zip`) — injector Zygisk.
   - Nếu máy đang có BreZygisk/ReZygisk: `touch /data/adb/modules/rezygisk/disable` trước, rồi cài NeoZygisk, reboot.
3. **HMA-OSS** — module Zygisk ẩn app list.
4. **Tricky Store** (AlwaysStrong) — keybox attestation.
5. **vneid_persist** (`modules/vneid_persist-v2.0.zip`) — dọn prop + sus_path.

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

NeoZygisk nạp lại y nguyên các Zygisk module cũ (`tricky_store`, `hma_oss_zygisk`,
`zygisk_vector`) — không cần cấu hình lại. Kernel SuSFS không bị đụng.

---

## 4. Trị theo từng app (checklist Zimperium)

### VNeID (`com.vnid`) — CA-E012 custom-ROM
- Cần: kernel SuSFS wildcard v3 + `vneid_persist` (nạp `add_sus_path_loop` các path `*lineage*`
  + 5 file `*debug*.rc`). Kernel v3 tự re-flag `path+map` mỗi lần Zygote fork app → miễn nhiễm
  `icache` eviction, không cần cron.
- HMA: để **Blacklist**, preset `[custom_rom, root_apps, sus_apps, xposed]`.

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
update: làm **manual**, và nếu commit kernel đổi thì **build lại kernel** từ `~/kbuild/kernel`
(coi chừng lệch ABI `.ko`).

---

_Ghi chú build: boot v3 SHA256 `afccf86ce48f36f483d32863355726f89a847125b4be6f1ecd99e0eeb09c72db`,
ABI diff vs base = 0 dòng, kernel `#7 SMP PREEMPT`._
