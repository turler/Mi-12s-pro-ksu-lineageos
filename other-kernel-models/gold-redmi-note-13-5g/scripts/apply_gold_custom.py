#!/usr/bin/env python3
"""Apply clean 6.6.143 custom kernel adaptations on top of e9ba38a48ac0."""
import pathlib

ROOT = pathlib.Path("/home/minhdc/kbuild-gold/kernel")


def edit(rel: str, old: str, new: str, count: int = 1) -> None:
    p = ROOT / rel
    s = p.read_text()
    assert s.count(old) == count, f"{rel}: expected {count} match (got {s.count(old)}) for:\n{old[:160]}"
    p.write_text(s.replace(old, new))


# 1. include/linux/susfs_def.h
edit(
    "include/linux/susfs_def.h",
    "#define TIF_PROC_UMOUNTED_FOR_ZYGOTE_NEXT 35\n",
    "#define TIF_PROC_UMOUNTED_FOR_ZYGOTE_NEXT 35\n#define TIF_PROC_UNTRUSTED_APP 36\n",
)
edit(
    "include/linux/susfs_def.h",
    "#define SUSFS_IS_INODE_SUS_MAP(inode) \\",
    """static inline bool susfs_is_current_untrusted_umounted_app(void) {
\treturn (likely(test_thread_flag(TIF_PROC_UMOUNTED)) &&
\t\tlikely(test_thread_flag(TIF_PROC_UNTRUSTED_APP)) &&
\t\t((current_uid().val % 100000) >= 10000));
}

static inline bool susfs_is_task_untrusted_umounted_app(struct task_struct *task) {
\tif (unlikely(!task))
\t\treturn false;
\treturn (test_ti_thread_flag(task_thread_info(task), TIF_PROC_UMOUNTED) &&
\t\ttest_ti_thread_flag(task_thread_info(task), TIF_PROC_UNTRUSTED_APP) &&
\t\t((__kuid_val(task_uid(task)) % 100000) >= 10000));
}

static inline bool susfs_is_untrusted_secctx(const char *str, size_t size) {
\tif (!str || !size)
\t\treturn false;
\treturn ((size >= 17 && !memcmp(str, "u:r:untrusted_app", 17)) ||
\t\t(size >= 16 && !memcmp(str, "u:r:isolated_app", 16)));
}

static inline bool susfs_is_cusrom_name_len(const char *name, int len) {
\tint i;
\tif (unlikely(!name || len < 7))
\t\treturn false;
\tif (unlikely(len == 7 && !memcmp(name, "addon.d", 7)))
\t\treturn true;
\tif (unlikely(len == 13 && !memcmp(name, "init-debug.rc", 13)))
\t\treturn true;
\tif (unlikely(len == 14 && !memcmp(name, "gps_debug.conf", 14)))
\t\treturn true;
\tif (unlikely(len == 17 && (!memcmp(name, "bootstat-debug.rc", 17) ||
\t\t\t\t   !memcmp(name, "qmipriod.debug.rc", 17))))
\t\treturn true;
\tif (unlikely(len == 19 && !memcmp(name, "atrace_userdebug.rc", 19)))
\t\treturn true;
\tfor (i = 0; i <= len - 7; i++) {
\t\tif (((name[i]   | 0x20) == 'l') &&
\t\t    ((name[i+1] | 0x20) == 'i') &&
\t\t    ((name[i+2] | 0x20) == 'n') &&
\t\t    ((name[i+3] | 0x20) == 'e') &&
\t\t    ((name[i+4] | 0x20) == 'a') &&
\t\t    ((name[i+5] | 0x20) == 'g') &&
\t\t    ((name[i+6] | 0x20) == 'e'))
\t\t\treturn true;
\t}
\treturn false;
}

static inline bool susfs_is_cusrom_idmap_len(const char *name, int len) {
\treturn (len > 13 &&
\t\t!memcmp(name + len - 6, "@idmap", 6) &&
\t\tsusfs_is_cusrom_name_len(name, len));
}

#define SUSFS_IS_INODE_SUS_MAP(inode) \\""",
)

# 2. fs/susfs.c
edit(
    "fs/susfs.c",
    """\t\t\t\tset_bit(AS_FLAGS_SUS_PATH, &inode->i_mapping->flags);
\t\t\t\tSUSFS_LOGI("re-flag AS_FLAGS_SUS_PATH on path '%s', inode->i_ino: '%lu', inode->i_mapping->flags: 0x%lx\\n",""",
    """\t\t\t\tset_bit(AS_FLAGS_SUS_PATH, &inode->i_mapping->flags);
\t\t\t\tset_bit(AS_FLAGS_SUS_MAP, &inode->i_mapping->flags);
\t\t\t\tSUSFS_LOGI("re-flag AS_FLAGS_SUS_PATH on path '%s', inode->i_ino: '%lu', inode->i_mapping->flags: 0x%lx\\n",""",
)
edit(
    "fs/susfs.c",
    """int susfs_get_data_path(struct path *path) {
\treturn kern_path("/data", LOOKUP_FOLLOW, path);
}
#endif // #ifdef CONFIG_KSU_SUSFS_SUS_PATH""",
    """int susfs_get_data_path(struct path *path) {
\treturn kern_path("/data", LOOKUP_FOLLOW, path);
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
bool susfs_is_dentry_sus_path(struct mnt_idmap *idmap, struct dentry *dentry)
#else
bool susfs_is_dentry_sus_path(struct dentry *dentry)
#endif
{
\tstruct inode *inode;
\tconst unsigned char *name;
\tunsigned int len;

\tif (!dentry)
\t\treturn false;
\tinode = READ_ONCE(dentry->d_inode);
\tif (!inode)
\t\treturn false;
\tif (susfs_is_current_untrusted_umounted_app() &&
\t    __kuid_val(inode->i_uid) < 10000) {
\t\trcu_read_lock();
\t\tname = READ_ONCE(dentry->d_name.name);
\t\tlen = READ_ONCE(dentry->d_name.len);
\t\tif (sb_rdonly(dentry->d_sb)) {
\t\t\tif (unlikely(susfs_is_cusrom_name_len((const char *)name, len))) {
\t\t\t\trcu_read_unlock();
\t\t\t\treturn true;
\t\t\t}
\t\t} else if (unlikely(susfs_is_cusrom_idmap_len((const char *)name, len))) {
\t\t\trcu_read_unlock();
\t\t\treturn true;
\t\t}
\t\trcu_read_unlock();
\t}
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
\treturn susfs_is_inode_sus_path(idmap, inode);
#else
\treturn susfs_is_inode_sus_path(inode);
#endif
}
#endif // #ifdef CONFIG_KSU_SUSFS_SUS_PATH""",
)
edit(
    "fs/susfs.c",
    """bool susfs_is_priority_uid_filtered(uid_t uid) {
\tstruct susfs_priority_uid_filter_bitmap *bitmap;

\tuid_t app_id = uid % 100000;

\tif (app_id < SUSFS_PRIORITY_UID_FILTER_MIN_UID ||
\t\tapp_id > SUSFS_PRIORITY_UID_FILTER_MAX_UID)
\t\treturn false;""",
    """bool susfs_is_priority_uid_filtered(uid_t uid) {
\tstruct susfs_priority_uid_filter_bitmap *bitmap;
\tuid_t app_id;

\tif (uid == current_uid().val)
\t\treturn false;

\tapp_id = uid % 100000;

\tif (app_id < SUSFS_PRIORITY_UID_FILTER_MIN_UID ||
\t\tapp_id > SUSFS_PRIORITY_UID_FILTER_MAX_UID)
\t\treturn false;

\tif (susfs_is_current_untrusted_umounted_app())
\t\treturn true;""",
)

# 3. fs/namei.c
edit(
    "fs/namei.c",
    "extern bool susfs_is_inode_sus_path(struct mnt_idmap* idmap, struct inode *inode);\n",
    "extern bool susfs_is_inode_sus_path(struct mnt_idmap* idmap, struct inode *inode);\nextern bool susfs_is_dentry_sus_path(struct mnt_idmap* idmap, struct dentry *dentry);\n",
)
edit(
    "fs/namei.c",
    "\tif (dentry && !IS_ERR(dentry) && dentry->d_inode && susfs_is_inode_sus_path(&nop_mnt_idmap, dentry->d_inode)) {",
    "\tif (dentry && !IS_ERR(dentry) && dentry->d_inode && susfs_is_dentry_sus_path(&nop_mnt_idmap, dentry)) {",
)
edit(
    "fs/namei.c",
    "\tif (unlikely(dentry) && !IS_ERR(dentry) && dentry->d_inode && !found_sus_path && susfs_is_inode_sus_path(&nop_mnt_idmap, dentry->d_inode)) {",
    "\tif (unlikely(dentry) && !IS_ERR(dentry) && dentry->d_inode && !found_sus_path && susfs_is_dentry_sus_path(&nop_mnt_idmap, dentry)) {",
)
edit(
    "fs/namei.c",
    "\tbool is_nd_state_lookup_last_and_open_last = (nd->state & (ND_STATE_LOOKUP_LAST | ND_STATE_OPEN_LAST));\n",
    "\t(void)nd;\n",
)
edit(  # RCU and non-RCU branches of lookup_fast share this exact block
    "fs/namei.c",
    """\t\tif (is_nd_state_lookup_last_and_open_last && dentry && !IS_ERR(dentry) && dentry->d_inode &&
\t\t\tsusfs_is_inode_sus_path(&nop_mnt_idmap, dentry->d_inode))""",
    """\t\tif (dentry && !IS_ERR(dentry) && READ_ONCE(dentry->d_inode) &&
\t\t\tsusfs_is_dentry_sus_path(&nop_mnt_idmap, dentry))""",
    count=2,
)
edit(
    "fs/namei.c",
    "\tbool found_sus_path = false;\n\tbool is_nd_flags_lookup_last = (flags & ND_FLAGS_LOOKUP_LAST);\n",
    "\tbool found_sus_path = false;\n",
)
edit(
    "fs/namei.c",
    """\tif (is_nd_flags_lookup_last && !found_sus_path && dentry && !IS_ERR(dentry) && dentry->d_inode &&
\t\tsusfs_is_inode_sus_path(&nop_mnt_idmap, dentry->d_inode))""",
    """\tif (!found_sus_path && dentry && !IS_ERR(dentry) && READ_ONCE(dentry->d_inode) &&
\t\tsusfs_is_dentry_sus_path(&nop_mnt_idmap, dentry))""",
)
edit(
    "fs/namei.c",
    "\t\tif (dentry->d_inode && susfs_is_inode_sus_path(&nop_mnt_idmap, dentry->d_inode)) {",
    "\t\tif (dentry->d_inode && susfs_is_dentry_sus_path(&nop_mnt_idmap, dentry)) {",
)
edit(
    "fs/namei.c",
    """\tif (is_nd_state_open_last && dentry && !IS_ERR(dentry) && dentry->d_inode &&
\t\tsusfs_is_inode_sus_path(&nop_mnt_idmap, dentry->d_inode))""",
    """\tif (is_nd_state_open_last && dentry && !IS_ERR(dentry) && dentry->d_inode &&
\t\tsusfs_is_dentry_sus_path(&nop_mnt_idmap, dentry))""",
)

# 4. fs/readdir.c (all 5 actors return bool in 6.6)
edit(
    "fs/readdir.c",
    """\tif (buf->result)
\t\treturn false;
\tbuf->result = verify_dirent_name(name, namlen);
\tif (buf->result)
\t\treturn false;
\td_ino = ino;""",
    """\tif (buf->result)
\t\treturn false;
\tbuf->result = verify_dirent_name(name, namlen);
\tif (buf->result)
\t\treturn false;
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
\tif (susfs_is_current_untrusted_umounted_app() &&
\t    buf->sb && (sb_rdonly(buf->sb) ?
\t\t\tsusfs_is_cusrom_name_len(name, namlen) :
\t\t\tsusfs_is_cusrom_idmap_len(name, namlen)))
\t\treturn true;
#endif
\td_ino = ino;""",
    count=2,  # fillonedir + compat_fillonedir (identical preamble in 6.6.143)
)
# filldir and filldir64 and compat_filldir share this exact 5-line preamble (3 matches)
p_rd = ROOT / "fs/readdir.c"
s_rd = p_rd.read_text()
target_rd = """\tbuf->error = verify_dirent_name(name, namlen);
\tif (unlikely(buf->error))
\t\treturn false;
\tbuf->error = -EINVAL;\t/* only used if we fail.. */"""
repl_rd = """\tbuf->error = verify_dirent_name(name, namlen);
\tif (unlikely(buf->error))
\t\treturn false;
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
\tif (susfs_is_current_untrusted_umounted_app() &&
\t    buf->sb && (sb_rdonly(buf->sb) ?
\t\t\tsusfs_is_cusrom_name_len(name, namlen) :
\t\t\tsusfs_is_cusrom_idmap_len(name, namlen)))
\t\treturn true;
#endif
\tbuf->error = -EINVAL;\t/* only used if we fail.. */"""
assert s_rd.count(target_rd) == 3, f"expected 3 matches in readdir.c, got {s_rd.count(target_rd)}"
s_rd = s_rd.replace(target_rd, repl_rd)
p_rd.write_text(s_rd)

# 5. fs/proc/base.c & fs/proc/task_mmu.c
VMA_HELPER = """#include <linux/susfs_def.h>
static inline bool susfs_is_vma_file_sus_map(struct file *f) {
\tstruct inode *inode;
\tstruct dentry *dentry;
\tconst unsigned char *name;
\tunsigned int len;
\tbool match = false;
\tif (!f)
\t\treturn false;
\tinode = file_inode(f);
\tif (SUSFS_IS_INODE_SUS_MAP(inode))
\t\treturn true;
\tif (!inode || !susfs_is_current_untrusted_umounted_app() || __kuid_val(inode->i_uid) >= 10000)
\t\treturn false;
\tdentry = f->f_path.dentry;
\tif (!dentry)
\t\treturn false;
\trcu_read_lock();
\tname = READ_ONCE(dentry->d_name.name);
\tlen = READ_ONCE(dentry->d_name.len);
\tif (sb_rdonly(inode->i_sb))
\t\tmatch = unlikely(susfs_is_cusrom_name_len((const char *)name, len));
\telse
\t\tmatch = unlikely(susfs_is_cusrom_idmap_len((const char *)name, len));
\trcu_read_unlock();
\treturn match;
}"""
edit("fs/proc/base.c", "#include <linux/susfs_def.h>", VMA_HELPER)
edit("fs/proc/base.c", "if (SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))", "if (susfs_is_vma_file_sus_map(vma->vm_file))")

edit("fs/proc/task_mmu.c", "#include <linux/susfs_def.h>", VMA_HELPER)
edit("fs/proc/task_mmu.c", "\t\tif (SUSFS_IS_INODE_SUS_MAP(inode))\n\t\t\treturn;", "\t\tif (susfs_is_vma_file_sus_map(vma->vm_file))\n\t\t\treturn;")
edit("fs/proc/task_mmu.c", "\t\tif (SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))\n\t\t\treturn 0;", "\t\tif (susfs_is_vma_file_sus_map(vma->vm_file))\n\t\t\treturn 0;")
edit("fs/proc/task_mmu.c", "\t\tif (vma->vm_file && SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))", "\t\tif (vma->vm_file && susfs_is_vma_file_sus_map(vma->vm_file))")
edit("fs/proc/task_mmu.c", "\t\t\t\tif (!vma->vm_file || !(SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))) {", "\t\t\t\tif (!vma->vm_file || !(susfs_is_vma_file_sus_map(vma->vm_file))) {")
edit("fs/proc/task_mmu.c", "\t\tif (vma && vma->vm_file && SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))", "\t\tif (vma && vma->vm_file && susfs_is_vma_file_sus_map(vma->vm_file))")

# 6. security/selinux/hooks.c
edit(
    "security/selinux/hooks.c",
    '#include "avc.h"\n',
    '#include "avc.h"\n#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs_def.h>\n#endif\n',
)
edit(
    "security/selinux/hooks.c",
    "\t\ttsec->sid = sid;\n\t} else {\n\t\terror = -EINVAL;\n\t\tgoto abort_change;",
    """\t\ttsec->sid = sid;
#ifdef CONFIG_KSU_SUSFS
\t\t{
\t\t\tstruct task_struct *t;
\t\t\tbool is_untrusted = susfs_is_untrusted_secctx(str, size);
\t\t\trcu_read_lock();
\t\t\tfor_each_thread(current, t) {
\t\t\t\tif (is_untrusted)
\t\t\t\t\tset_ti_thread_flag(task_thread_info(t), TIF_PROC_UNTRUSTED_APP);
\t\t\t\telse
\t\t\t\t\tclear_ti_thread_flag(task_thread_info(t), TIF_PROC_UNTRUSTED_APP);
\t\t\t}
\t\t\trcu_read_unlock();
\t\t}
#endif
\t} else {
\t\terror = -EINVAL;
\t\tgoto abort_change;""",
)

# 7. drivers/kernelsu/feature/selinux_hide.c
edit(
    "drivers/kernelsu/feature/selinux_hide.c",
    '#include "avc.h"\n',
    '#include "avc.h"\n#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs_def.h>\n#include <linux/sched/signal.h>\n#endif\n',
)
edit(
    "drivers/kernelsu/feature/selinux_hide.c",
    "    tsec->sid = sid;\n\n    commit_creds(new);",
    """    tsec->sid = sid;
#ifdef CONFIG_KSU_SUSFS
    {
        struct task_struct *t;
        bool is_untrusted = susfs_is_untrusted_secctx(str, size);
        rcu_read_lock();
        for_each_thread(current, t) {
            if (is_untrusted)
                set_ti_thread_flag(task_thread_info(t), TIF_PROC_UNTRUSTED_APP);
            else
                clear_ti_thread_flag(task_thread_info(t), TIF_PROC_UNTRUSTED_APP);
        }
        rcu_read_unlock();
    }
#endif
    commit_creds(new);""",
)

# 8. drivers/kernelsu/hook/setuid_hook.c (for_each_thread)
edit(
    "drivers/kernelsu/hook/setuid_hook.c",
    """    if (susfs_is_current_zygote_domain()) {
        if (is_isolated_process(new_uid) ||
            (is_appuid(new_uid) && ksu_uid_should_umount(new_uid))) {
            susfs_set_current_proc_no_su();
            susfs_set_current_proc_umounted();""",
    """    if (susfs_is_current_zygote_domain()) {
        if (is_isolated_process(new_uid) ||
            (is_appuid(new_uid) && ksu_uid_should_umount(new_uid))) {
            {
                struct task_struct *t;
                rcu_read_lock();
                for_each_thread(current, t) {
                    set_ti_thread_flag(task_thread_info(t), TIF_PROC_NO_SU);
                    set_ti_thread_flag(task_thread_info(t), TIF_PROC_UMOUNTED);
                }
                rcu_read_unlock();
            }""",
)
edit(
    "drivers/kernelsu/hook/setuid_hook.c",
    """    } else if (susfs_is_current_zygote_next_domain()) {
        if (is_isolated_process(new_uid) ||
            (is_appuid(new_uid) && ksu_uid_should_umount(new_uid))) {
            susfs_set_current_proc_no_su();
            susfs_set_current_proc_umounted();""",
    """    } else if (susfs_is_current_zygote_next_domain()) {
        if (is_isolated_process(new_uid) ||
            (is_appuid(new_uid) && ksu_uid_should_umount(new_uid))) {
            {
                struct task_struct *t;
                rcu_read_lock();
                for_each_thread(current, t) {
                    set_ti_thread_flag(task_thread_info(t), TIF_PROC_NO_SU);
                    set_ti_thread_flag(task_thread_info(t), TIF_PROC_UMOUNTED);
                }
                rcu_read_unlock();
            }""",
)

# 9. drivers/android/binder.c
edit(
    "drivers/android/binder.c",
    "static void binder_transaction(struct binder_proc *proc,",
    """#ifdef CONFIG_KSU_SUSFS
#include <linux/susfs_def.h>
#include <linux/mm.h>

static bool susfs_utf16_eq_ascii(const u8 *p, u32 char_len, const char *ascii, u32 alen)
{
\tu32 i;
\tif (char_len != alen)
\t\treturn false;
\tfor (i = 0; i < alen; i++) {
\t\tif (p[i * 2] != (u8)ascii[i] || p[i * 2 + 1] != 0)
\t\t\treturn false;
\t}
\treturn true;
}

static bool susfs_utf16_has_lineage(const u8 *p, u32 char_len)
{
\tu32 k;
\tif (char_len < 7)
\t\treturn false;
\tfor (k = 0; k <= char_len - 7; k++) {
\t\tconst u8 *q = p + k * 2;
\t\tif (q[1] == 0 && q[3] == 0 && q[5] == 0 && q[7] == 0 &&
\t\t    q[9] == 0 && q[11] == 0 && q[13] == 0 &&
\t\t    ((q[0]  | 0x20) == 'l') && ((q[2]  | 0x20) == 'i') &&
\t\t    ((q[4]  | 0x20) == 'n') && ((q[6]  | 0x20) == 'e') &&
\t\t    ((q[8]  | 0x20) == 'a') && ((q[10] | 0x20) == 'g') &&
\t\t    ((q[12] | 0x20) == 'e'))
\t\t\treturn true;
\t}
\treturn false;
}

static bool susfs_utf16_scrub_lineage(u8 *p, u32 char_len)
{
\tstatic const char repl[7] = { 'a', 'n', 'd', 'r', 'o', 'i', 'd' };
\tu32 k, j;
\tbool changed = false;

\tif (char_len < 7)
\t\treturn false;
\tfor (k = 0; k <= char_len - 7; k++) {
\t\tu8 *q = p + k * 2;
\t\tif (q[1] == 0 && q[3] == 0 && q[5] == 0 && q[7] == 0 &&
\t\t    q[9] == 0 && q[11] == 0 && q[13] == 0 &&
\t\t    ((q[0]  | 0x20) == 'l') && ((q[2]  | 0x20) == 'i') &&
\t\t    ((q[4]  | 0x20) == 'n') && ((q[6]  | 0x20) == 'e') &&
\t\t    ((q[8]  | 0x20) == 'a') && ((q[10] | 0x20) == 'g') &&
\t\t    ((q[12] | 0x20) == 'e')) {
\t\t\tfor (j = 0; j < 7; j++) {
\t\t\t\tq[j * 2] = (u8)repl[j];
\t\t\t\tq[j * 2 + 1] = 0;
\t\t\t}
\t\t\tchanged = true;
\t\t\tk += 6;
\t\t}
\t}
\treturn changed;
}

static void susfs_scrub_servicemanager_txn(struct binder_proc *proc,
\t\t\t\t\t   struct binder_proc *target_proc,
\t\t\t\t\t   struct binder_thread *target_thread,
\t\t\t\t\t   struct binder_node *target_node,
\t\t\t\t\t   struct binder_context *context,
\t\t\t\t\t   struct binder_transaction *t,
\t\t\t\t\t   struct binder_transaction_data *tr,
\t\t\t\t\t   bool reply)
{
\tsize_t dsize;

\tif (unlikely(!context || !context->binder_context_mgr_node || !t || !t->buffer))
\t\treturn;
\tif (tr->offsets_size != 0)
\t\treturn;
\tdsize = (size_t)tr->data_size;

\tif (!reply) {
\t\tu8 sbuf[512];
\t\tsize_t off;

\t\tif (target_node != context->binder_context_mgr_node)
\t\t\treturn;
\t\tif (dsize < 68 || dsize > sizeof(sbuf))
\t\t\treturn;
\t\tif (!susfs_is_current_untrusted_umounted_app())
\t\t\treturn;
\t\tif (binder_alloc_copy_from_buffer(&target_proc->alloc, sbuf, t->buffer, 0, dsize))
\t\t\treturn;

\t\tfor (off = 0; off <= 32 && off + 60 <= dsize; off += 4) {
\t\t\tu32 dlen;
\t\t\tsize_t arg_off;
\t\t\ts32 slen;
\t\t\tsize_t sbytes;
\t\t\tu8 *sp;

\t\t\tmemcpy(&dlen, sbuf + off, sizeof(dlen));
\t\t\tif (dlen != 26)
\t\t\t\tcontinue;
\t\t\tif (!susfs_utf16_eq_ascii(sbuf + off + 4, 26, "android.os.IServiceManager", 26))
\t\t\t\tcontinue;
\t\t\tif (sbuf[off + 4 + 52] != 0 || sbuf[off + 4 + 53] != 0)
\t\t\t\tcontinue;

\t\t\targ_off = off + 4 + 56;
\t\t\tif (arg_off + 4 > dsize)
\t\t\t\treturn;
\t\t\tmemcpy(&slen, sbuf + arg_off, sizeof(slen));
\t\t\tif (slen < 7 || slen > 200)
\t\t\t\treturn;
\t\t\tsbytes = ((size_t)slen + 1) * 2;
\t\t\tif (arg_off + 4 + sbytes > dsize)
\t\t\t\treturn;
\t\t\tsp = sbuf + arg_off + 4;
\t\t\tif (sp[(size_t)slen * 2] != 0 || sp[(size_t)slen * 2 + 1] != 0)
\t\t\t\treturn;

\t\t\tif (susfs_utf16_eq_ascii(sp, (u32)slen, "profile", 7) ||
\t\t\t    susfs_utf16_has_lineage(sp, (u32)slen)) {
\t\t\t\tu8 under[2] = { '_', 0 };
\t\t\t\t(void)binder_alloc_copy_to_buffer(&target_proc->alloc,
\t\t\t\t\t\t\t\t  t->buffer, arg_off + 4,
\t\t\t\t\t\t\t\t  under, sizeof(under));
\t\t\t}
\t\t\treturn;
\t\t}
\t} else {
\t\tstruct binder_node *mgr;
\t\tbool is_sm;
\t\ts32 hdr[2];
\t\ts32 count, i;
\t\tsize_t pos;
\t\tu8 *kbuf;
\t\tbool dirty = false;

\t\tif (dsize < 16 || dsize > 131072)
\t\t\treturn;
\t\tif (!target_thread || !susfs_is_task_untrusted_umounted_app(target_thread->task))
\t\t\treturn;
\t\tmutex_lock(&context->context_mgr_node_lock);
\t\tmgr = context->binder_context_mgr_node;
\t\tis_sm = mgr && mgr->proc == proc;
\t\tmutex_unlock(&context->context_mgr_node_lock);
\t\tif (!is_sm)
\t\t\treturn;
\t\tif (binder_alloc_copy_from_buffer(&target_proc->alloc, hdr, t->buffer, 0, sizeof(hdr)))
\t\t\treturn;
\t\tif (hdr[0] != 0 || hdr[1] < 16 || hdr[1] > 4096)
\t\t\treturn;
\t\tcount = hdr[1];

\t\tkbuf = kvmalloc(dsize, GFP_KERNEL);
\t\tif (!kbuf)
\t\t\treturn;
\t\tif (binder_alloc_copy_from_buffer(&target_proc->alloc, kbuf, t->buffer, 0, dsize)) {
\t\t\tkvfree(kbuf);
\t\t\treturn;
\t\t}

\t\tpos = 8;
\t\tfor (i = 0; i < count; i++) {
\t\t\ts32 slen;
\t\t\tsize_t sbytes;

\t\t\tif (pos + 4 > dsize)
\t\t\t\tgoto out_free;
\t\t\tmemcpy(&slen, kbuf + pos, sizeof(slen));
\t\t\tpos += 4;
\t\t\tif (slen == -1)
\t\t\t\tcontinue;
\t\t\tif (slen < 0 || slen > 1024)
\t\t\t\tgoto out_free;
\t\t\tsbytes = ALIGN(((size_t)slen + 1) * 2, 4);
\t\t\tif (pos + sbytes > dsize)
\t\t\t\tgoto out_free;
\t\t\tif (kbuf[pos + (size_t)slen * 2] != 0 ||
\t\t\t    kbuf[pos + (size_t)slen * 2 + 1] != 0)
\t\t\t\tgoto out_free;
\t\t\tpos += sbytes;
\t\t}
\t\tif (dsize - pos > 16)
\t\t\tgoto out_free;

\t\tpos = 8;
\t\tfor (i = 0; i < count; i++) {
\t\t\ts32 slen;
\t\t\tsize_t sbytes;
\t\t\tu8 *sp;

\t\t\tmemcpy(&slen, kbuf + pos, sizeof(slen));
\t\t\tpos += 4;
\t\t\tif (slen == -1)
\t\t\t\tcontinue;
\t\t\tsbytes = ALIGN(((size_t)slen + 1) * 2, 4);
\t\t\tsp = kbuf + pos;
\t\t\tif (slen >= 7) {
\t\t\t\tif (susfs_utf16_eq_ascii(sp, (u32)slen, "profile", 7)) {
\t\t\t\t\tstatic const char sp_repl[7] = { 's', 'y', 's', 'p', 'r', 'o', 'f' };
\t\t\t\t\tu32 j;
\t\t\t\t\tfor (j = 0; j < 7; j++) {
\t\t\t\t\t\tsp[j * 2] = (u8)sp_repl[j];
\t\t\t\t\t\tsp[j * 2 + 1] = 0;
\t\t\t\t\t}
\t\t\t\t\tdirty = true;
\t\t\t\t} else if (susfs_utf16_scrub_lineage(sp, (u32)slen)) {
\t\t\t\t\tdirty = true;
\t\t\t\t}
\t\t\t}
\t\t\tpos += sbytes;
\t\t}

\t\tif (dirty) {
\t\t\t(void)binder_alloc_copy_to_buffer(&target_proc->alloc,
\t\t\t\t\t\t\t  t->buffer, 0, kbuf, dsize);
\t\t}
out_free:
\t\tkvfree(kbuf);
\t}
}
#endif /* CONFIG_KSU_SUSFS */

static void binder_transaction(struct binder_proc *proc,""",
)
edit(
    "drivers/android/binder.c",
    """\tif (t->buffer->oneway_spam_suspect)
\t\ttcomplete->type = BINDER_WORK_TRANSACTION_ONEWAY_SPAM_SUSPECT;""",
    """#ifdef CONFIG_KSU_SUSFS
\tsusfs_scrub_servicemanager_txn(proc, target_proc, target_thread,
\t\t\t\t       target_node, context, t, tr, reply);
#endif
\tif (t->buffer->oneway_spam_suspect)
\t\ttcomplete->type = BINDER_WORK_TRANSACTION_ONEWAY_SPAM_SUSPECT;""",
)

print("ALL CUSTOM PATCHES APPLIED CLEANLY")
