#include "save.h"
#include "nb.h"
#include "vm.h"
#include "hal.h"
#include "nb_vars.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include <time.h>

static SaveData *sd = NULL;

static void save_collect(SaveData *s)
{
    int i;
    s->magic = SAVE_MAGIC;
    s->version = SAVE_VERSION;
    s->checksum = 0;
    nb_get_state(s->filename, sizeof(s->filename),
                 s->lang, sizeof(s->lang),
                 s->chapter_title, sizeof(s->chapter_title));
    {
        const int *v = nb_var_get_state();
        for (i = 0; i < NB_VAR_COUNT; i++)
            s->var_values[i] = v[i];
    }
}

static void save_apply(const SaveData *s)
{
    nb_var_set_state(s->var_values);
    nb_set_lang(s->lang);
    nb_load(s->filename);
    /* Mark the loaded scene as unlocked */
    {
        unsigned int scene_id;
        if (sscanf(s->filename, "nbook%u.nb", &scene_id) == 1)
            sys_save_unlock_scene((int)scene_id);
    }
}

static int save_write(const char *path, SaveData *s)
{
    if (save_file_write(path, s, sizeof(SaveData), SAVE_MAGIC, SAVE_VERSION,
                        offsetof(SaveData, checksum), "[SAVE]") != 0)
        return -1;
    hal_log("[SAVE] wrote ok\r\n");
    return 0;
}

static int save_read(const char *path, SaveData *s)
{
    /* SAVE_VERSION 2 files use the pre-chapter_title layout: everything up
     * to (but excluding) chapter_title.  Parameterized here instead of a
     * hardcoded size so field reordering keeps the older layout match. */
    if (save_file_read(path, s, sizeof(SaveData),
                       offsetof(SaveData, chapter_title),
                       SAVE_MAGIC, SAVE_VERSION,
                       offsetof(SaveData, checksum), "[SAVE]") != 0)
        return -1;
    if (s->version < SAVE_VERSION_MIN) {
        hal_log("[SAVE] unsupported version\r\n");
        return -1;
    }
    /* Defence-in-depth: files are checksum-validated, but a valid file may
     * still hold a full-width string with no NUL; terminate the buffers. */
    s->filename[sizeof(s->filename) - 1] = '\0';
    s->lang[sizeof(s->lang) - 1] = '\0';
    s->chapter_title[sizeof(s->chapter_title) - 1] = '\0';
    hal_log("[SAVE] read ok\r\n");
    return 0;
}

static void slot_path(int slot, char *buf, int bufsz)
{
    snprintf(buf, bufsz, "SAVE%02d.SAV", slot);
}

const char *save_get_filename(void)
{
    if (!sd) return NULL;
    return sd->filename;
}

int save_game_temp(void)
{
    if (!sd) {
        sd = (SaveData *)malloc(sizeof(SaveData));
        if (!sd) { hal_log("[SAVE] temp malloc fail\r\n"); return -1; }
    }
    save_collect(sd);
    hal_log("[SAVE] temp saved to memory\r\n");
    return 0;
}

void save_game_slot(int slot)
{
    char path[32];
    if (slot < 0 || slot >= SAVE_SLOTS) {
        hal_log("[SAVE] invalid slot\r\n");
        return;
    }
    if (!sd) {
        sd = (SaveData *)malloc(sizeof(SaveData));
        if (!sd) { hal_log("[SAVE] slot malloc fail\r\n"); return; }
    }
    /* Re-collect every save: sd may outlive a prior save_collect() call,
     * and re-saving must write the current (not stale) game state. */
    save_collect(sd);
    snprintf(sd->slot_name, sizeof(sd->slot_name), "Slot %d", slot + 1);
    {
        time_t t = time(NULL);
        struct tm *tm = localtime(&t);
        if (tm)
            snprintf(sd->timestamp, sizeof(sd->timestamp),
                     "%04d-%02d-%02d %02d:%02d:%02d",
                     tm->tm_year + 1900, tm->tm_mon + 1, tm->tm_mday,
                     tm->tm_hour, tm->tm_min, tm->tm_sec);
        else
            snprintf(sd->timestamp, sizeof(sd->timestamp), "(no rtc)");
    }
    slot_path(slot, path, sizeof(path));
    if (save_write(path, sd) != 0)
        hal_log("[SAVE] slot write failed\r\n");
}

int load_game_temp(void)
{
    if (!sd) { hal_log("[SAVE] temp load: sd is NULL\r\n"); return -1; }
    save_apply(sd);
    hal_log("[SAVE] temp restored from memory\r\n");
    return 0;
}

int load_game_slot(int slot)
{
    char path[32];
    if (slot < 0 || slot >= SAVE_SLOTS) {
        hal_log("[LOAD] invalid slot\r\n");
        return -1;
    }
    if (!sd) {
        sd = (SaveData *)malloc(sizeof(SaveData));
        if (!sd) { hal_log("[LOAD] slot malloc fail\r\n"); return -1; }
    }
    slot_path(slot, path, sizeof(path));
    { char _b[96]; snprintf(_b, sizeof(_b), "[LOAD] load_game_slot(%d) path=%s\r\n", slot, path); hal_log(_b); }
    if (save_read(path, sd) != 0) {
        hal_log("[LOAD] save_read failed\r\n");
        return -1;
    }
    { char _b[96]; snprintf(_b, sizeof(_b), "[LOAD] filename='%s' ver=%u\r\n", sd->filename, sd->version); hal_log(_b); }
    save_apply(sd);
    if (vm_get_flags() & VMFLAG_ERROR) {
        hal_log("[LOAD] nb_load failed (VMFLAG_ERROR)\r\n");
        vm_clear_error();
        return -1;
    }
    return 0;
}

int slot_info(int slot, SlotInfo *info)
{
    char path[32];
    unsigned int magic;
    char slot_name[32], timestamp[20];
    FILE *f;

    if (slot < 0 || slot >= SAVE_SLOTS) return 0;
    info->exists = 0;
    info->version = 0;
    snprintf(info->slot_name, sizeof(info->slot_name), "Slot %d — (Empty)", slot + 1);
    info->timestamp[0] = '\0';
    info->filename[0] = '\0';
    info->chapter_title[0] = '\0';

    slot_path(slot, path, sizeof(path));
    f = fopen(path, "rb");
    if (!f) return 0;

    if (fread(&magic, sizeof(magic), 1, f) != 1) { fclose(f); return 0; }
    if (fread(&info->version, sizeof(info->version), 1, f) != 1) { fclose(f); return 0; }
    if (fread(slot_name, sizeof(slot_name), 1, f) != 1) { fclose(f); return 0; }
    if (fread(timestamp, sizeof(timestamp), 1, f) != 1) { fclose(f); return 0; }
    /* skip past checksum + var_values to reach filename */
    {
        int skip = (int)(offsetof(SaveData, filename) - offsetof(SaveData, checksum));
        if (fseek(f, skip, SEEK_CUR) != 0) { fclose(f); return 0; }
    }
    if (fread(info->filename, sizeof(info->filename), 1, f) != 1) { fclose(f); return 0; }
    /* skip lang[] between filename and chapter_title */
    {
        int lang_skip = (int)(offsetof(SaveData, chapter_title) - offsetof(SaveData, lang));
        if (fseek(f, lang_skip, SEEK_CUR) != 0) { fclose(f); return 0; }
    }
    /* read chapter_title for v3+ */
    if (info->version >= 3) {
        if (fread(info->chapter_title, sizeof(info->chapter_title), 1, f) != 1)
            info->chapter_title[0] = '\0';
    }

    fclose(f);

    if (magic != SAVE_MAGIC) return 0;

    info->exists = 1;
    strncpy(info->slot_name, slot_name, sizeof(info->slot_name) - 1);
    info->slot_name[sizeof(info->slot_name) - 1] = '\0';
    strncpy(info->timestamp, timestamp, sizeof(info->timestamp) - 1);
    info->timestamp[sizeof(info->timestamp) - 1] = '\0';
    info->filename[sizeof(info->filename) - 1] = '\0';
    info->chapter_title[sizeof(info->chapter_title) - 1] = '\0';
    return 1;
}


