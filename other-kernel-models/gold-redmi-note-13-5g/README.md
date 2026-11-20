# gold — Redmi Note 13 5G (2312DRAABC) · GKI android15-6.6.143 + KernelSU-Next + SuSFS

Source của kernel tự build cho máy `gold` (MediaTek, Android 17), dạng **chuỗi patch** trên upstream — không kèm cả cây kernel.

- **Base:** `android.googlesource.com/kernel/common`, commit `1a04d7d18c1d` (`6.6.143-android15-8`)
- **Thêm vào:** KernelSU-Next v3.4.2 (built-in) + SuSFS v2.3.0 (gki-android15-6.6) + chỉnh sửa riêng cho gold
- **kernelrelease:** `6.6.143-android15-8-g1a04d7d18c1d-ab16867777-4k`
- **Toolchain:** Android clang r596125 (clang 22.0.2)

## Nội dung

```
patches/   git format-patch 1a04d7d18c1d..8f9433315fab (5 commit, áp bằng git am)
configs/   gold-base.config, ksu-susfs.config, stock_module_signing_cert.pem (chứng chỉ công khai)
scripts/   build.sh, apply_gold_custom.py, crc_gate.py, modcrc.py, susfs_sanitize.py,
           gki_module_crc_check.py, gki_module_sig_check.py
reports/   REPORT_GOLD.md, REPORT_GOLD_FIX1.md (nhật ký build/kiểm tra)
```

## Dựng lại

```
git clone https://android.googlesource.com/kernel/common kernel && cd kernel
git checkout 1a04d7d18c1d
git am ../patches/*.patch
```
Các script còn đường dẫn cứng `/home/minhdc/kbuild-gold` và `SYSTEM_TRUSTED_KEYS` trỏ vào `configs/stock_module_signing_cert.pem`: sửa lại cho đúng máy build.

## Điều kiện bắt buộc (đã gây bootloop khi thiếu)

1. `CONFIG_CC_HAS_COUNTED_BY` phải tắt (patch 0004). Clang mới làm lệch CRC của `icc_*` so với module stock, init panic ở ~3 s.
2. `CONFIG_SYSTEM_TRUSTED_KEYS` phải chứa cert ký module stock. Nếu rỗng, `MODULE_SIG_PROTECT` từ chối module GKI của Google và wifi mất.
3. Trước khi flash phải chạy gate CRC và gate chữ ký trên mọi module stock (vendor_boot, vendor_dlkm, system_dlkm).
4. Kernel có KSU built-in nên phải làm sạch KSU LKM trong ramdisk `vendor_boot`. Nếu không, hai KSU cùng nạp.

## Trạng thái

- Build `work/final` đã chạy trên máy gold, `vpnhide_kmod` v1.3.1 (android15-6.6) nạp được bằng `insmod`.
- Chưa kèm boot image / AnyKernel zip. Boot image nằm ở máy build, cần dựng lại hoặc xuất riêng.
- Kernel chỉ dùng cho đúng máy gold. Không flash lên máy khác.
