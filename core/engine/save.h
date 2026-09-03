#ifndef SAVE_H
#define SAVE_H

#include <stddef.h>
#include "nb_var_table.h"

#define SAVE_SLOTS          12
#define SAVE_MAGIC          0x4E41495A
#define SYSTEM_SAVE_MAGIC   0x5953544D
#define SAVE_VERSION        3
/* SAVE_VERSION_MIN 2: v2 save layout = current SaveData minus chapter_title.
 * save_read() reads exactly offsetof(SaveData, chapter_title) bytes for a
 * v2 file so the older format stays loadable.  Bump SAVE_VERSION when the
 * struct layout changes; keep MIN at the oldest still-loadable layout. */
#define SAVE_VERSION_MIN    2
#define CG_TOTAL            99
#define ENDING_TOTAL        16
#define SCENE_TOTAL         100
#define CG_FLAG_WORDS       ((CG_TOTAL + 31) / 32)
#define ENDING_FLAG_WORDS   ((ENDING_TOTAL + 31) / 32)
#define SCENE_FLAG_WORDS    ((SCENE_TOTAL + 31) / 32)

typedef struct {
    unsigned int magic;
    unsigned int version;
    char         slot_name[32];
    char         timestamp[20];
    unsigned int checksum;
    int          var_values[NB_VAR_COUNT];
    char         filename[64];
    char         lang[8];
    char         chapter_title[64];
} SaveData;

typedef struct {
    int     exists;
    unsigned int version;
    char    slot_name[32];
    char    timestamp[20];
    char    filename[64];
    char    chapter_title[64];
} SlotInfo;

typedef struct {
    unsigned int magic;
    unsigned int version;
    unsigned int checksum;
    unsigned int cg_flags[CG_FLAG_WORDS];
    unsigned int ending_flags[ENDING_FLAG_WORDS];
    unsigned int clear_count;
    unsigned int scene_flags[SCENE_FLAG_WORDS];
    unsigned int reserved[32 - SCENE_FLAG_WORDS];
} SystemSave;

/* Shared save I/O helpers (implemented in save_io.c) */
int save_file_write(const char *path, void *data, size_t sz,
                    unsigned int magic, unsigned int version,
                    size_t cs_offset, const char *tag);
int save_file_read(const char *path, void *buf, size_t bufsz, size_t min_size,
                   unsigned int expected_magic, unsigned int max_version,
                   size_t cs_offset, const char *tag);

const char *save_get_filename(void);
int  save_game_temp(void);
void save_game_slot(int slot);
int  load_game_temp(void);
int  load_game_slot(int slot);
int  slot_info(int slot, SlotInfo *info);

void sys_save_load(void);
void sys_save_unlock_scene(int scene_id);
void sys_save_unlock_cg(int cg_id);
int  sys_save_is_cg_unlocked(int cg_id);

#endif
