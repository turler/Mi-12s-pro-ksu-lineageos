#!/usr/bin/env bash
# Build kernel 4.19.325-cip137-st21 + KernelSU-Next (legacy UAPI v6) + SuSFS v1.5.5 for Xiaomi Redmi Note 11 (spes)
set -euo pipefail

WORKDIR="${WORKDIR:-$PWD/spes-kernel-build}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_DIR="$(dirname "$SCRIPT_DIR")"

mkdir -p "$WORKDIR" && cd "$WORKDIR"

if [ ! -d kernel ]; then
  git clone --depth=1 -b prebuilt https://github.com/Shaddowalker-26/android_kernel_xiaomi_spes.git kernel
  (cd kernel && git apply "$MODEL_DIR/patches/0001-spes-kernel-4.19-ksun-susfs-v1.5.5-selinux-cusrom-v8.patch")
fi

if [ ! -d KernelSU-Next ]; then
  git clone --depth=1 -b legacy https://github.com/KernelSU-Next/KernelSU-Next.git KernelSU-Next
  (cd KernelSU-Next && git apply "$MODEL_DIR/patches/0002-ksunext-legacy-susfs-bridge-selinux-hide-setuid-v8.patch")
fi

ln -sfn ../../KernelSU-Next/kernel kernel/drivers/kernelsu

mkdir -p out
make -C kernel O="$WORKDIR/out" ARCH=arm64 CC=clang LLVM=1 LLVM_IAS=1 vendor/bengal-perf_defconfig
kernel/scripts/kconfig/merge_config.sh -m -O "$WORKDIR/out" \
  "$WORKDIR/out/.config" \
  kernel/arch/arm64/configs/vendor/xiaomi/spes.config \
  "$MODEL_DIR/configs/ksu-susfs.config"
make -C kernel O="$WORKDIR/out" ARCH=arm64 CC=clang LLVM=1 LLVM_IAS=1 olddefconfig
make -C kernel O="$WORKDIR/out" -j"$(nproc)" \
  ARCH=arm64 CC=clang LLVM=1 LLVM_IAS=1 \
  CROSS_COMPILE=aarch64-linux-gnu- \
  CROSS_COMPILE_ARM32=arm-linux-gnueabi- \
  Image.gz

echo "Built: $WORKDIR/out/arch/arm64/boot/Image.gz"
