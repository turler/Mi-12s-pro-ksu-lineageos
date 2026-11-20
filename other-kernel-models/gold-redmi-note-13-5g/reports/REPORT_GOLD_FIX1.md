# gold fix1 (after bootloop of boot_gold_ksun_susfs.img 55463420…)

Bootloop cause (pstore console-ramoops, kernel_panic,init at ~3.19 s):
`mmqos_common: disagrees about version of symbol of_icc_get / icc_set_bw` -> init failed to load first-stage modules -> panic.

Root cause: clang 22 enables CONFIG_CC_HAS_COUNTED_BY (stock was clang 18). `struct icc_path { ... reqs[] __counted_by(num_nodes) }`
changes the genksyms type string, so CRCs of of_icc_get, icc_set_bw, icc_put, devm_of_icc_get differ from the stock modules.
The earlier "100% CRC match" only checked CPU_DVFS.ko and base-vs-final symvers (both built with clang 22).

Fixes:
1. kernel commit 648b959f7bc5: `depends on BROKEN` for CC_HAS_COUNTED_BY.
2. CONFIG_SYSTEM_TRUSTED_KEYS = stock module signing cert (extracted from stock Image, serial 704BAB37…), so the 79
   Google-signed GKI modules (bluetooth, wwan, btqca, l2tp, …) keep sig_ok under MODULE_SIG_PROTECT.

Gates (all PASS):
- scripts/crc_gate.py: 444 stock modules (184 vendor_boot first-stage + vendor_dlkm/system_dlkm/vendor), 21789 refs, 0 mismatches.
- 79/79 signed stock modules verify with the stock cert embedded in the new Image.
- 365 unsigned vendor modules: 0 uses of vmlinux symbols outside the unprotected list.
- kernelrelease 6.6.143-android15-8-g1a04d7d18c1d-ab16867777-4k; repacked on the device's current boot_b (a0e72989…).
