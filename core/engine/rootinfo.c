#include <stdint.h>
#include "hal.h"
#include "log.h"
#include "stdbuffer.h"
#include "rootinfo.h"

RootInfo root_info;

static const char magic_mhvn[4] = {'M', 'H', 'V', 'N'};

int read_root_info(void)
{
    for (unsigned int i = 0; i < sizeof(RootInfo); i++)
        ((unsigned char*)&root_info)[i] = 0;

    int fd = hal_file_open("ROOTINFO.DAT", 0);
    if (fd < 0)
    {
        log_write("ERR: ROOTINFO.DAT not found\r\n");
        return -1;
    }
    int br = hal_file_read(fd, small_file_buffer, 0x76);
    if (br < 0x76)
    {
        hal_file_close(fd);
        return -1;
    }
    for (int i = 0; i < 4; i++)
    {
        if (small_file_buffer[i] != magic_mhvn[i])
        {
            log_write("ERR: bad magic in ROOTINFO.DAT\r\n");
            hal_file_close(fd);
            return -1;
        }
    }
    root_info.vn_flags         = *((unsigned short*)(small_file_buffer + 0x04));
    root_info.num_stvar_glob   = *((unsigned short*)(small_file_buffer + 0x06));
    root_info.num_flags_glob   = *((unsigned short*)(small_file_buffer + 0x08));
    root_info.num_stvar_loc    = *((unsigned short*)(small_file_buffer + 0x0A));
    root_info.num_flags_loc    = *((unsigned short*)(small_file_buffer + 0x0C));
    root_info.def_fmt_normal   = *((unsigned short*)(small_file_buffer + 0x0E));
    root_info.def_fmt_charname = *((unsigned short*)(small_file_buffer + 0x10));
    root_info.def_fmt_menu     = *((unsigned short*)(small_file_buffer + 0x12));
    root_info.def_fmt_menu_sel = *((unsigned short*)(small_file_buffer + 0x14));
    for (int i = 0; i < 12; i++)
    {
        root_info.font_path[i]     = small_file_buffer[0x16 + i];
        root_info.scene_path[i]    = small_file_buffer[0x22 + i];
        root_info.lang_path[i]     = small_file_buffer[0x2E + i];
        root_info.bg_path[i]       = small_file_buffer[0x3A + i];
        root_info.sprite_path[i]   = small_file_buffer[0x46 + i];
        root_info.music_path[i]    = small_file_buffer[0x52 + i];
        root_info.sfx_path[i]      = small_file_buffer[0x5E + i];
        root_info.sys_path[i]      = small_file_buffer[0x6A + i];
    }
    hal_file_close(fd);
    return 0;
}

int init_language(unsigned short lang)
{
    int fd = hal_file_open(root_info.lang_path, 0);
    if (fd < 0)
    {
        log_write("ERR: lang file not found\r\n");
        return -1;
    }
    int br = hal_file_read(fd, small_file_buffer, 1024);
    hal_file_close(fd);
    if (br < 4) return -1;

    root_info.num_lang = *((unsigned short*)(small_file_buffer));
    root_info.cur_lang = lang;
    unsigned char* td = small_file_buffer + small_file_buffer[2 + 4 * lang];
    for (unsigned int i = 0; i < 12; i++)
    {
        if (td[i]) root_info.cur_text_path[i] = td[i];
        else break;
    }
    return 0;
}

int change_language(unsigned short new_lang)
{
    if (new_lang == root_info.cur_lang) return 0;
    return init_language(new_lang);
}
