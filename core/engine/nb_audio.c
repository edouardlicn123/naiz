/*
 * nb_audio.c — NB audio commands (bgm/sound/voice).
 *
 * Split from nb_commands.c: audio commands depend only on hal.h, forming
 * a distinct feature track (backend implementation plan: devdocs doc-41).
 * Registered in nb_commands.c cmd_table.
 */
#include <string.h>
#include "hal.h"
#include "nb_internal.h"
#include "nb_commands.h"

void cmd_bgm(int argc, const char **argv, const char *cmd_name)
{
    (void)argc; (void)cmd_name;
    if (argc < 1) return;
    if (strcmp(argv[0], "stop") == 0)
        hal_bgm_stop();
    else
        hal_bgm_play(argv[0]);
}

void cmd_sound(int argc, const char **argv, const char *cmd_name)
{
    (void)argc; (void)cmd_name;
    if (argc < 1) return;
    hal_sound_play(argv[0]);
}

void cmd_voice(int argc, const char **argv, const char *cmd_name)
{
    (void)argc; (void)cmd_name;
    if (argc < 1) return;
    hal_voice_play(argv[0]);
}
