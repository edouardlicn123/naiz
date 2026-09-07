/*
 * nb_audio.c — NB audio commands (bgm/sound/voice).
 *
 * Split from nb_commands.c: audio commands depend only on hal.h, forming
 * a distinct feature track (backend implementation plan: devdocs doc-41).
 * Registered in nb_commands.c cmd_table.
 * Grammar (mirrors cmd_cg): {key} is the brace payload; parens are reserved
 * for parameters.  bgm(stop) is a keyword directive.
 */
#include <stdio.h>
#include <string.h>
#include "hal.h"
#include "nb_internal.h"
#include "nb_commands.h"
#include "debug.h"

void cmd_bgm(int argc, const char **argv, const char *cmd_name)
{
    (void)cmd_name;
    if (argc < 1) return;
    if (argc == 1 && strcmp(argv[0], "stop") == 0) {
        hal_bgm_stop();
        return;
    }
    if (nb_get_last_brace_arg() != argc - 1) {
        NB_DEBUG("bgm: usage bgm(){key} | bgm(stop)\r\n");
        return;
    }
    hal_bgm_play(argv[argc - 1]);
}

void cmd_sound(int argc, const char **argv, const char *cmd_name)
{
    (void)cmd_name;
    if (argc < 1) return;
    if (nb_get_last_brace_arg() != argc - 1) {
        NB_DEBUG("sound: usage sound(){key}\r\n");
        return;
    }
    hal_sound_play(argv[argc - 1]);
}

void cmd_voice(int argc, const char **argv, const char *cmd_name)
{
    (void)cmd_name;
    if (argc < 1) return;
    if (nb_get_last_brace_arg() != argc - 1) {
        NB_DEBUG("voice: usage voice(){key}\r\n");
        return;
    }
    hal_voice_play(argv[argc - 1]);
}
