#!/usr/bin/env bash
# usage: build.sh <outdir-name> [extra config fragments...]   (builds Image + modules)
set -euo pipefail
R=/home/minhdc/kbuild-gold
. $R/env.sh
O=$R/work/$1; shift
mkdir -p "$O"
M=(make -C $R/kernel O=$O ARCH=arm64 LLVM=1 LLVM_IAS=1 CC=clang)
export LOCALVERSION=
cp $R/work/abi_symbollist.raw $O/abi_symbollist.raw
printf '%s' '-android15-8-g1a04d7d18c1d-ab16867777' > $O/localversion
if [ ! -f $O/.config ]; then
  "${M[@]}" -s gki_defconfig
  (cd $R/kernel && scripts/kconfig/merge_config.sh -m -O "$O" "$O/.config" $R/configs/gold-base.config "$@")
  "${M[@]}" -s olddefconfig
fi
echo "kernelrelease: $("${M[@]}" -s kernelrelease)"
"${M[@]}" -j16 Image modules 2>&1 | tail -n 60
