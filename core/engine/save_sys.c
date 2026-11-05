/*
 * save_sys.c — System save (CG/ending/scene unlock flags, clear count).
 *
 * Split from save.c: independent from slot save/load, no shared state.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "save.h"
#include "hal.h"

#define SYSPATH "SYSTEM.SAV"

static SystemSave sys_sd;

static int sys_write(const char *path, SystemSave *s)
{
    if (save_file_write(path, s, sizeof(SystemSave), SYSTEM_SAVE_MAGIC, SAVE_VERSION,
                        offsetof(SystemSave, checksum), "[SYS]") != 0)
        return -1;
    hal_log("[SYS] wrote ok\r\n");
    return 0;
}

static int sys_read(const char *path, SystemSave *s)
{
    if (save_file_read(path, s, sizeof(SystemSave), sizeof(SystemSave),
                       SYSTEM_SAVE_MAGIC, SAVE_VERSION,
                       offsetof(SystemSave, checksum), "[SYS]") != 0)
        return -1;
    return 0;
}

void sys_save_load(void)
{
    memset(&sys_sd, 0, sizeof(sys_sd));
    if (sys_read(SYSPATH, &sys_sd) != 0) {
        hal_log("[SYS] no system save, using defaults\r\n");
        memset(&sys_sd, 0, sizeof(sys_sd));
        sys_sd.magic = SYSTEM_SAVE_MAGIC;
        sys_sd.version = SAVE_VERSION;
    }
}

static void sys_save_write(void)
{
    sys_write(SYSPATH, &sys_sd);
}

void sys_save_unlock_scene(int scene_id)
{
    if (scene_id < 1 || scene_id > SCENE_TOTAL) return;
    sys_sd.scene_flags[(scene_id - 1) / 32] |= (1u << ((scene_id - 1) % 32));
    sys_save_write();
}

/* Unlock a CG (1..CG_TOTAL) in SYSTEM.SAV and flush to disk. */
void sys_save_unlock_cg(int cg_id)
{
    if (cg_id < 1 || cg_id > CG_TOTAL) return;
    sys_sd.cg_flags[(cg_id - 1) / 32] |= (1u << ((cg_id - 1) % 32));
    sys_save_write();
}

/* Return non-zero when CG cg_id has been unlocked. */
int sys_save_is_cg_unlocked(int cg_id)
{
    if (cg_id < 1 || cg_id > CG_TOTAL) return 0;
    return (sys_sd.cg_flags[(cg_id - 1) / 32] & (1u << ((cg_id - 1) % 32))) != 0;
}
