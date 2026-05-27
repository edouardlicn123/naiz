#ifndef ROOTINFO_H
#define ROOTINFO_H

typedef struct
{
    unsigned short vn_flags;
    unsigned short num_stvar_glob;
    unsigned short num_flags_glob;
    unsigned short num_stvar_loc;
    unsigned short num_flags_loc;
    unsigned short def_fmt_normal;
    unsigned short def_fmt_charname;
    unsigned short def_fmt_menu;
    unsigned short def_fmt_menu_sel;
    unsigned short num_lang;
    unsigned short cur_lang;
    char font_path[13];
    char scene_path[13];
    char lang_path[13];
    char cur_text_path[13];
    char bg_path[13];
    char sprite_path[13];
    char music_path[13];
    char sfx_path[13];
    char sys_path[13];
} RootInfo;

extern RootInfo root_info;

int read_root_info(void);
int init_language(unsigned short lang);
int change_language(unsigned short new_lang);

#endif
