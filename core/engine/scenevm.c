#include "hal.h"
#include "memalloc.h"
#include "pc98_egc.h"
#include "pc98_gdc.h"
#include "x86strops.h"
#include "lz4.h"
#include "stdbuffer.h"
#include "rootinfo.h"
#include "scenevm.h"
#include "textengine.h"
#include "palette.h"
#include "graphics.h"

#define VMFLAG_Z         0x01
#define VMFLAG_N         0x02
#define VMFLAG_TEXTINBOX 0x40
#define VMFLAG_PROCESS   0x80

#define ASYNC_FADE    0x01
#define ASYNC_PALETTE 0x02
#define ASYNC_SCROLL  0x04
#define ASYNC_USER    0x80

#define AFADE_BFADEIN    1
#define AFADE_BFADEOUT   2
#define AFADE_WFADEIN    3
#define AFADE_WFADEOUT   4
#define AFADE_PHUEROTATE 5

#define APAL_PFADEIN    1
#define APAL_PFADEOUT   2

#define ASCR_SHAKE 1

#define SVAR_BASE    0x0000
#define SFLG_BASE    0x0008
#define GVAR_BASE    0x0020
#define GFLG_BASE    0x0100
#define LVAR_BASE    0x0400
#define LFLG_BASE    0x0600
#define VARSPACE_TOP 0x1000

#define STYPE_YNCHOICE 0
#define STYPE_CHOICE2  1
#define STYPE_CHOICE3  2
#define STYPE_CHOICE4  3

SceneInfo scene_info;
unsigned char cur_scene_data[4096];
unsigned short cur_scene_data_pc;
unsigned char vm_flags;

unsigned char cur_async_actions;
unsigned char cur_async_fade_action;
short cur_bfade_amt;
short cur_wfade_amt;
short cur_fade_target;
short cur_fade_speed;
unsigned short cur_hue_rotation_factor;
unsigned short cur_hue_rotation_speed;

unsigned char cur_async_palette_action;
short cur_pfade_amt;
short cur_palette_fade_target;
short cur_palette_fade_speed;

unsigned char cur_async_scroll_action;
short cur_shake_amp;
unsigned short cur_shake_adv;
short cur_shake_damp_factor;
unsigned short cur_shake_point;

int return_status;
unsigned char selection_type;
char selected_option;
unsigned short selected_var;
unsigned short selected_first_text;
unsigned short cur_char_num;
unsigned short next_text_num;
char cur_char_name[64];
unsigned int cur_text_array[256];
char __far* scene_text_buffer = 0;

short scratch_vars[8];
short global_vars[224];
short local_vars[512];
unsigned char scratch_flags[3];
unsigned char global_flags[96];
unsigned char local_flags[320];

static int load_new_scene(unsigned short scene_num)
{
    if (scene_num == scene_info.cur_scene) return 0;
    unsigned long curpos;
    unsigned long scenedatpos;
    int fh = hal_file_open(root_info.scene_path, 0);
    if (fh < 0)
    {
        write_string("Error! Could not find scene data file!", 168, 184, FORMAT_SHADOW | FORMAT_COLOUR_SET(0xF), 0);
        return -1;
    }
    hal_file_seek(fh, 0, 4 + 4 * scene_num, &curpos);
    hal_file_read(fh, &scenedatpos, 4);
    hal_file_seek(fh, 0, 4 + 4 * scene_info.num_scenes + scenedatpos, &curpos);
    unsigned long comp_size;
    hal_file_read(fh, &comp_size, 4);
    unsigned char __far* decompbuf = mem_alloc(comp_size + 4);
    { unsigned long fa = (unsigned long)(decompbuf + 4);
      hal_file_read_far(fh, fa >> 16, fa & 0xFFFF, comp_size); }
    hal_file_close(fh);
    *((unsigned long __far*)decompbuf) = comp_size;
    lz4_decompress(decompbuf, cur_scene_data, comp_size);
    mem_free(decompbuf);
    int res = load_scene_text(scene_num, scene_text_buffer, cur_text_array);
    if (res) return res;
    cur_scene_data_pc = 0;
    return_status = 0;
    cur_char_num = 0xFFFF;
    cur_async_actions = 0;
    cur_fade_target = 0;
    cur_bfade_amt = 0;
    cur_wfade_amt = 0;
    cur_hue_rotation_factor = 0;
    cur_palette_fade_target = 0;
    cur_pfade_amt = 0;
    vm_flags = VMFLAG_PROCESS;
    return 0;
}

int setup_scene_engine(void)
{
    int fh = hal_file_open(root_info.scene_path, 0);
    if (fh < 0)
    {
        write_string("Error! Could not find scene data file!", 168, 184, FORMAT_SHADOW | FORMAT_COLOUR_SET(0xF), 0);
        return -1;
    }
    hal_file_read(fh, small_file_buffer, 4);
    scene_info.num_scenes = *((unsigned short*)(small_file_buffer));
    scene_info.num_chars = *((unsigned short*)(small_file_buffer + 2));
    scene_text_buffer = mem_alloc(0x10000);
    scene_info.cur_scene = 0xFFFF;
    hal_file_close(fh);
    return load_new_scene(0);
}

int free_scene_engine(void)
{
    if (scene_text_buffer == 0) return 0;
    mem_free(scene_text_buffer);
    scene_text_buffer = 0;
    return 0;
}

static short* get_variable_ref(unsigned short addr)
{
    if (addr < SFLG_BASE) return scratch_vars + addr;
    else if (addr < GVAR_BASE) return (short*)0;
    else if (addr < GFLG_BASE) return global_vars + addr - GVAR_BASE;
    else if (addr < LVAR_BASE) return (short*)0;
    else if (addr < LFLG_BASE) return local_vars + addr - LVAR_BASE;
    else return (short*)0;
}

static unsigned char get_flag(unsigned short addr)
{
    unsigned short val = 0;
    if (addr < SFLG_BASE) val = scratch_vars[addr];
    else if (addr < GVAR_BASE)
    {
        addr -= SFLG_BASE;
        val = scratch_flags[addr >> 3];
        val &= (0x01 << (addr & 0x7));
    }
    else if (addr < GFLG_BASE) val = global_vars[addr - GVAR_BASE];
    else if (addr < LVAR_BASE)
    {
        addr -= GFLG_BASE;
        val = global_flags[addr >> 3];
        val &= (0x01 << (addr & 0x7));
    }
    else if (addr < LFLG_BASE) val = local_vars[addr - LVAR_BASE];
    else if (addr < VARSPACE_TOP)
    {
        addr -= LFLG_BASE;
        val = local_flags[addr >> 3];
        val &= (0x01 << (addr & 0x7));
    }
    else return 0;
    return val != 0;
}

static void set_flag(unsigned short addr, unsigned char val)
{
    unsigned char* flgptr;
    unsigned char flgval;
    if (addr < SFLG_BASE) return;
    else if (addr < GVAR_BASE)
    {
        addr -= SFLG_BASE;
        flgptr = scratch_flags + (addr >> 3);
    }
    else if (addr < GFLG_BASE) return;
    else if (addr < LVAR_BASE)
    {
        addr -= GFLG_BASE;
        flgptr = global_flags + (addr >> 3);
    }
    else if (addr < LFLG_BASE) return;
    else if (addr < VARSPACE_TOP)
    {
        addr -= LFLG_BASE;
        flgptr = local_flags + (addr >> 3);
    }
    else return;
    flgval = *flgptr;
    unsigned char flgsel = (0x01 << (addr & 0x7));
    val = (val != 0) << (addr & 0x7);
    flgval &= ~flgsel;
    flgval |= val;
    *flgptr = flgval;
}

void control_process(unsigned char process)
{
    if (process) vm_flags |= VMFLAG_PROCESS;
    else vm_flags &= ~VMFLAG_PROCESS;
}

static void clear_text_box(void)
{
    draw_9slice_box_inner_region(text_box_img_info);
}

static void clear_character_name(void)
{
    draw_9slice_box_inner_region(char_name_box_img_info);
}

void switch_choice(char dir)
{
    selected_option += dir;
    int cx = choice_box_inner_bounds.pos.x;
    int cy = choice_box_inner_bounds.pos.y;
    draw_9slice_box_inner_region(choice_box_img_info);
    switch (selection_type)
    {
        case STYPE_YNCHOICE:
            if (selected_option < 0) selected_option = 1;
            else if (selected_option > 1) selected_option = 0;
            if (selected_option)
            {
                write_string("Yes", cx, cy, root_info.def_fmt_menu_sel, 0);
                write_string("No", cx, cy + 16, root_info.def_fmt_menu, 0);
            }
            else
            {
                write_string("Yes", cx, cy, root_info.def_fmt_menu, 0);
                write_string("No", cx, cy + 16, root_info.def_fmt_menu_sel, 0);
            }
            break;
        case STYPE_CHOICE2:
            if (selected_option < 0) selected_option = 1;
            else if (selected_option > 1) selected_option = 0;
            if (selected_option)
            {
                write_string(scene_text_buffer + cur_text_array[selected_first_text], cx, cy, root_info.def_fmt_menu, 0);
                write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], cx, cy + 16, root_info.def_fmt_menu_sel, 0);
            }
            else
            {
                write_string(scene_text_buffer + cur_text_array[selected_first_text], cx, cy, root_info.def_fmt_menu_sel, 0);
                write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], cx, cy + 16, root_info.def_fmt_menu, 0);
            }
            break;
        case STYPE_CHOICE3:
            if (selected_option < 0) selected_option = 2;
            else if (selected_option > 2) selected_option = 0;
            switch (selected_option)
            {
                case 0:
                    write_string(scene_text_buffer + cur_text_array[selected_first_text], cx, cy, root_info.def_fmt_menu_sel, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], cx, cy + 16, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 2], cx, cy + 32, root_info.def_fmt_menu, 0);
                    break;
                case 1:
                    write_string(scene_text_buffer + cur_text_array[selected_first_text], cx, cy, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], cx, cy + 16, root_info.def_fmt_menu_sel, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 2], cx, cy + 32, root_info.def_fmt_menu, 0);
                    break;
                case 2:
                    write_string(scene_text_buffer + cur_text_array[selected_first_text], cx, cy, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], cx, cy + 16, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 2], cx, cy + 32, root_info.def_fmt_menu_sel, 0);
                    break;
            }
            break;
        case STYPE_CHOICE4:
            if (selected_option < 0) selected_option = 3;
            else if (selected_option > 3) selected_option = 0;
            switch (selected_option)
            {
                case 0:
                    write_string(scene_text_buffer + cur_text_array[selected_first_text], cx, cy, root_info.def_fmt_menu_sel, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], cx, cy + 16, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 2], cx, cy + 32, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 3], cx, cy + 48, root_info.def_fmt_menu, 0);
                    break;
                case 1:
                    write_string(scene_text_buffer + cur_text_array[selected_first_text], cx, cy, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], cx, cy + 16, root_info.def_fmt_menu_sel, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 2], cx, cy + 32, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 3], cx, cy + 48, root_info.def_fmt_menu, 0);
                    break;
                case 2:
                    write_string(scene_text_buffer + cur_text_array[selected_first_text], cx, cy, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], cx, cy + 16, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 2], cx, cy + 32, root_info.def_fmt_menu_sel, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 3], cx, cy + 48, root_info.def_fmt_menu, 0);
                    break;
                case 3:
                    write_string(scene_text_buffer + cur_text_array[selected_first_text], cx, cy, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], cx, cy + 16, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 2], cx, cy + 32, root_info.def_fmt_menu, 0);
                    write_string(scene_text_buffer + cur_text_array[selected_first_text + 3], cx, cy + 48, root_info.def_fmt_menu_sel, 0);
                    break;
            }
            break;
    }
}

void commit_choice(void)
{
    short* var_ref;
    switch (selection_type)
    {
        case STYPE_YNCHOICE:
            if (selected_option) vm_flags |= VMFLAG_Z;
            else vm_flags &= ~VMFLAG_Z;
            break;
        case STYPE_CHOICE2:
        case STYPE_CHOICE3:
        case STYPE_CHOICE4:
            var_ref = get_variable_ref(selected_var);
            if (var_ref != 0) *var_ref = selected_option;
            break;
    }
    choice_box_img_info->flags &= ~IMAGE_DRAWREQ;
    egc_set_to_mono_draw_mode();
    return_status &= ~SCENE_STATUS_MAKING_CHOICE;
    control_process(1);
}

void end_user_wait(void)
{
    cur_async_actions &= ~ASYNC_USER;
}

static void do_brightness_fade(int is_black, int add, short step)
{
    if (is_black)
    {
        if (add) cur_bfade_amt += cur_fade_speed;
        else cur_bfade_amt -= cur_fade_speed;
        if (add ? (cur_bfade_amt >= cur_fade_target) : (cur_bfade_amt <= cur_fade_target))
        {
            cur_bfade_amt = cur_fade_target;
            cur_async_actions &= ~ASYNC_FADE;
        }
        set_display_palette_out_brightness(-(cur_bfade_amt >> 6));
    }
    else
    {
        if (add) cur_wfade_amt += cur_fade_speed;
        else cur_wfade_amt -= cur_fade_speed;
        if (add ? (cur_wfade_amt >= cur_fade_target) : (cur_wfade_amt <= cur_fade_target))
        {
            cur_wfade_amt = cur_fade_target;
            cur_async_actions &= ~ASYNC_FADE;
        }
        set_display_palette_out_brightness(cur_wfade_amt >> 6);
    }
}

void scene_async_action_process(void)
{
    unsigned char ca = cur_async_actions;

    if (ca & ASYNC_FADE)
    {
        unsigned char atype = cur_async_fade_action;
        switch (atype)
        {
            case AFADE_BFADEIN:  do_brightness_fade(1, 0, cur_fade_speed); break;
            case AFADE_BFADEOUT: do_brightness_fade(1, 1, cur_fade_speed); break;
            case AFADE_WFADEIN:  do_brightness_fade(0, 0, cur_fade_speed); break;
            case AFADE_WFADEOUT: do_brightness_fade(0, 1, cur_fade_speed); break;
            case AFADE_PHUEROTATE:
                cur_hue_rotation_factor += cur_hue_rotation_speed;
                set_display_palette_out_hue_rotate(cur_hue_rotation_factor);
                break;
            default: ca &= ~ASYNC_FADE; break;
        }
    }

    if (ca & ASYNC_PALETTE)
    {
        unsigned char atype = cur_async_palette_action;
        switch (atype)
        {
            case APAL_PFADEIN:
                cur_pfade_amt += cur_palette_fade_speed;
                if (cur_pfade_amt >= cur_palette_fade_target)
                {
                    cur_pfade_amt = cur_palette_fade_target;
                    ca &= ~ASYNC_PALETTE;
                }
                mix_palettes(cur_pfade_amt >> 6);
                break;
            case APAL_PFADEOUT:
                cur_pfade_amt -= cur_palette_fade_speed;
                if (cur_pfade_amt <= cur_palette_fade_target)
                {
                    cur_pfade_amt = cur_palette_fade_target;
                    ca &= ~ASYNC_PALETTE;
                }
                mix_palettes(cur_pfade_amt >> 6);
                break;
            default: ca &= ~ASYNC_PALETTE; break;
        }

        if (!(ca & ASYNC_FADE))
        {
            if (cur_bfade_amt != 0) set_display_palette_out_brightness(-(cur_bfade_amt >> 6));
            else if (cur_wfade_amt != 0) set_display_palette_out_brightness(cur_wfade_amt >> 6);
            else if (cur_hue_rotation_factor != 0) set_display_palette_out_hue_rotate(cur_hue_rotation_factor);
            else set_display_palette_out();
        }
    }

    if (ca & ASYNC_SCROLL)
    {
        unsigned char atype = cur_async_scroll_action;
        switch (atype)
        {
            case ASCR_SHAKE:
            {
                long cval = cos_fixed(((cur_shake_point >> 8) & 0x3FF) << 6);
                cval *= (long)cur_shake_amp;
                cval += 0x00200000;
                cval >>= 22;
                unsigned int sval = ((short)cval) + 400;
                gdc_scroll_simple_graphics(sval % 400);
                cur_shake_point += cur_shake_adv;
                long midamp = ((long)cur_shake_amp) * ((long)cur_shake_damp_factor);
                cur_shake_amp = (short)(midamp >> 14);
                if (cur_shake_amp < 0x0080)
                {
                    gdc_scroll_simple_graphics(0);
                    ca &= ~ASYNC_SCROLL;
                }
            }
                break;
            default: ca &= ~ASYNC_SCROLL; break;
        }
    }

    if (ca == 0) control_process(1);

    cur_async_actions = ca;
}

int scene_data_process(void)
{
    unsigned char cur_opcode;
    int result = 0;
    short* varptr1;
    short* varptr2;
    while (vm_flags & VMFLAG_PROCESS)
    {
        return_status = 0;
        cur_opcode = cur_scene_data[cur_scene_data_pc++];
        switch (cur_opcode)
        {
        case 0x00:
        {
            unsigned short sNum = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            if (sNum == 0xFFFF)
            {
                control_process(0);
                return_status |= SCENE_STATUS_FINALEND;
                break;
            }
            result = load_new_scene(sNum);
            if (result)
            {
                return_status = SCENE_STATUS_ERROR | result;
                control_process(0);
                break;
            }
            break;
        }
        case 0x01:
            cur_scene_data_pc += 2;
            cur_scene_data_pc += *((unsigned short*)(cur_scene_data + cur_scene_data_pc - 2));
            break;
        case 0x02:
            cur_scene_data_pc += 2;
            if (vm_flags & VMFLAG_Z) cur_scene_data_pc += *((unsigned short*)(cur_scene_data + cur_scene_data_pc - 2));
            break;
        case 0x03:
            cur_scene_data_pc += 2;
            if (!(vm_flags & VMFLAG_Z)) cur_scene_data_pc += *((unsigned short*)(cur_scene_data + cur_scene_data_pc - 2));
            break;
        case 0x04:
            cur_scene_data_pc += 2;
            if (vm_flags & VMFLAG_N) cur_scene_data_pc += *((unsigned short*)(cur_scene_data + cur_scene_data_pc - 2));
            break;
        case 0x05:
            cur_scene_data_pc += 2;
            if (!(vm_flags & VMFLAG_N)) cur_scene_data_pc += *((unsigned short*)(cur_scene_data + cur_scene_data_pc - 2));
            break;
        case 0x06:
            cur_scene_data_pc += 2;
            if (vm_flags & (VMFLAG_Z | VMFLAG_N)) cur_scene_data_pc += *((unsigned short*)(cur_scene_data + cur_scene_data_pc - 2));
            break;
        case 0x07:
            cur_scene_data_pc += 2;
            if (!(vm_flags & (VMFLAG_Z | VMFLAG_N))) cur_scene_data_pc += *((unsigned short*)(cur_scene_data + cur_scene_data_pc - 2));
            break;
        case 0x08:
            {
                unsigned short arg = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
                unsigned char r = (unsigned char)(arg & 0x001F);
                unsigned char g = (unsigned char)((arg >> 5) & 0x001F);
                unsigned char b = (unsigned char)((arg >> 10) & 0x001F);
                set_mix_single_colour_5bpc(r, g, b);
            }
            cur_scene_data_pc += 2;
            break;
        case 0x09:
            {
                unsigned short arg = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
                unsigned char r = (unsigned char)(arg & 0x001F);
                unsigned char g = (unsigned char)((arg >> 5) & 0x001F);
                unsigned char b = (unsigned char)((arg >> 10) & 0x001F);
                set_mix_main_add_5bpc(r, g, b);
            }
            cur_scene_data_pc += 2;
            break;
        case 0x0A:
            set_mix_luminosity_mod_8bpc(*(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 1;
            break;
        case 0x0B:
            set_mix_saturation_mod_8bpc(*(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 1;
            break;
        case 0x0C:
            set_mix_hue_mod_8bpc(*(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 1;
            break;
        case 0x0D:
            {
                unsigned short arg = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
                unsigned char r = (unsigned char)(arg & 0x001F);
                unsigned char g = (unsigned char)((arg >> 5) & 0x001F);
                unsigned char b = (unsigned char)((arg >> 10) & 0x001F);
                set_mix_colourised_5bpc(r, g, b);
            }
            cur_scene_data_pc += 2;
            break;
        case 0x0E:
            set_mix_invert();
            break;
        case 0x0F:
            break;
        case 0x11:
            if (vm_flags & VMFLAG_TEXTINBOX)
            {
                cur_scene_data_pc--;
                goto delText;
            }
            next_text_num = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
        case 0x10:
            if (vm_flags & VMFLAG_TEXTINBOX)
            {
                goto delText;
            }
            text_box_img_info->flags |= IMAGE_DRAWREQ;
            do_draw_requests();
            start_animated_string_write(scene_text_buffer + cur_text_array[next_text_num], text_box_inner_bounds.pos.x, text_box_inner_bounds.pos.y, root_info.def_fmt_normal);
            next_text_num++;
            vm_flags |= VMFLAG_TEXTINBOX;
            control_process(0);
            cur_async_actions |= ASYNC_USER;
            return_status |= SCENE_STATUS_RENDERTEXT;
            break;
        case 0x12:
        {
            unsigned short charNum = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            if (charNum != cur_char_num)
            {
                clear_character_name();
                if (charNum != 0xFFFF)
                {
                    result = load_current_character_name(charNum, cur_char_name);
                    char_name_box_img_info->flags |= IMAGE_DRAWREQ;
                    do_draw_requests();
                    if (result)
                    {
                        return_status = SCENE_STATUS_ERROR | result;
                        control_process(0);
                        break;
                    }
                    write_string(cur_char_name, char_name_box_inner_bounds.pos.x, char_name_box_inner_bounds.pos.y, root_info.def_fmt_charname, 0);
                }
                else
                {
                    char_name_box_img_info->flags &= ~IMAGE_DRAWREQ;
                }
                cur_char_num = charNum;
            }
            cur_scene_data_pc += 2;
            break;
        }
        case 0x13:
            delText:
            clear_text_box();
            vm_flags &= ~VMFLAG_TEXTINBOX;
            control_process(0);
            return_status |= SCENE_STATUS_WIPETEXT;
            break;
        case 0x14:
            selected_option = 1;
            selection_type = STYPE_YNCHOICE;
            control_process(0);
            cur_async_actions |= ASYNC_USER;
            return_status |= SCENE_STATUS_MAKING_CHOICE;
            choice_box_inner_bounds.size.y = 32;
            choice_box_img_info->boundRect.size.y = 64;
            choice_box_img_info->flags |= IMAGE_DRAWREQ;
            do_draw_requests();
            write_string("Yes", choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y, root_info.def_fmt_menu_sel, 0);
            write_string("No", choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y + 16, root_info.def_fmt_menu, 0);
            break;
        case 0x15:
            selected_option = 0;
            selection_type = STYPE_CHOICE2;
            control_process(0);
            cur_async_actions |= ASYNC_USER;
            return_status |= SCENE_STATUS_MAKING_CHOICE;
            selected_var = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            selected_first_text = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            choice_box_inner_bounds.size.y = 32;
            choice_box_img_info->boundRect.size.y = 64;
            choice_box_img_info->flags |= IMAGE_DRAWREQ;
            do_draw_requests();
            write_string(scene_text_buffer + cur_text_array[selected_first_text], choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y, root_info.def_fmt_menu_sel, 0);
            write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y + 16, root_info.def_fmt_menu, 0);
            break;
        case 0x16:
            selected_option = 0;
            selection_type = STYPE_CHOICE3;
            control_process(0);
            cur_async_actions |= ASYNC_USER;
            return_status |= SCENE_STATUS_MAKING_CHOICE;
            selected_var = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            selected_first_text = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            choice_box_inner_bounds.size.y = 48;
            choice_box_img_info->boundRect.size.y = 80;
            choice_box_img_info->flags |= IMAGE_DRAWREQ;
            do_draw_requests();
            write_string(scene_text_buffer + cur_text_array[selected_first_text], choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y, root_info.def_fmt_menu_sel, 0);
            write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y + 16, root_info.def_fmt_menu, 0);
            write_string(scene_text_buffer + cur_text_array[selected_first_text + 2], choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y + 32, root_info.def_fmt_menu, 0);
            break;
        case 0x17:
            selected_option = 0;
            selection_type = STYPE_CHOICE4;
            control_process(0);
            cur_async_actions |= ASYNC_USER;
            return_status |= SCENE_STATUS_MAKING_CHOICE;
            selected_var = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            selected_first_text = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            choice_box_inner_bounds.size.y = 64;
            choice_box_img_info->boundRect.size.y = 96;
            choice_box_img_info->flags |= IMAGE_DRAWREQ;
            do_draw_requests();
            write_string(scene_text_buffer + cur_text_array[selected_first_text], choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y, root_info.def_fmt_menu_sel, 0);
            write_string(scene_text_buffer + cur_text_array[selected_first_text + 1], choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y + 16, root_info.def_fmt_menu, 0);
            write_string(scene_text_buffer + cur_text_array[selected_first_text + 2], choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y + 32, root_info.def_fmt_menu, 0);
            write_string(scene_text_buffer + cur_text_array[selected_first_text + 3], choice_box_inner_bounds.pos.x, choice_box_inner_bounds.pos.y + 48, root_info.def_fmt_menu, 0);
            break;
        case 0x18:
            cur_async_actions |= ASYNC_FADE;
            if (cur_async_fade_action == AFADE_PHUEROTATE)
            {
                cur_hue_rotation_factor = 0;
                set_display_palette_out();
            }
            cur_async_fade_action = AFADE_BFADEIN;
            {
                unsigned char arg = *(cur_scene_data + cur_scene_data_pc);
                short amt = arg & 0x07;
                short speed = (arg >> 3) & 0x1F;
                if (cur_wfade_amt > 0) { cur_wfade_amt = 0; cur_fade_target = 0x3FC0; }
                cur_bfade_amt = cur_fade_target;
                cur_fade_target -= 0x07F8 * (amt + 1);
                if (cur_fade_target < 0) cur_fade_target = 0;
                cur_fade_speed = 0x0020 * (speed + 1);
            }
            cur_scene_data_pc += 1;
            goto decideWait;
        case 0x19:
            cur_async_actions |= ASYNC_FADE;
            if (cur_async_fade_action == AFADE_PHUEROTATE)
            {
                cur_hue_rotation_factor = 0;
                set_display_palette_out();
            }
            cur_async_fade_action = AFADE_BFADEOUT;
            {
                unsigned char arg = *(cur_scene_data + cur_scene_data_pc);
                short amt = arg & 0x07;
                short speed = (arg >> 3) & 0x1F;
                if (cur_wfade_amt > 0) { cur_wfade_amt = 0; cur_fade_target = 0; }
                cur_bfade_amt = cur_fade_target;
                cur_fade_target += 0x07F8 * (amt + 1);
                if (cur_fade_target > 0x3FC0) cur_fade_target = 0x3FC0;
                cur_fade_speed = 0x0020 * (speed + 1);
            }
            cur_scene_data_pc += 1;
            goto decideWait;
        case 0x1A:
            cur_async_actions |= ASYNC_FADE;
            if (cur_async_fade_action == AFADE_PHUEROTATE)
            {
                cur_hue_rotation_factor = 0;
                set_display_palette_out();
            }
            cur_async_fade_action = AFADE_WFADEIN;
            {
                unsigned char arg = *(cur_scene_data + cur_scene_data_pc);
                short amt = arg & 0x07;
                short speed = (arg >> 3) & 0x1F;
                if (cur_bfade_amt > 0) { cur_bfade_amt = 0; cur_fade_target = 0x3FC0; }
                cur_wfade_amt = cur_fade_target;
                cur_fade_target -= 0x07F8 * (amt + 1);
                if (cur_fade_target < 0) cur_fade_target = 0;
                cur_fade_speed = 0x0020 * (speed + 1);
            }
            cur_scene_data_pc += 1;
            goto decideWait;
        case 0x1B:
            cur_async_actions |= ASYNC_FADE;
            if (cur_async_fade_action == AFADE_PHUEROTATE)
            {
                cur_hue_rotation_factor = 0;
                set_display_palette_out();
            }
            cur_async_fade_action = AFADE_WFADEOUT;
            {
                unsigned char arg = *(cur_scene_data + cur_scene_data_pc);
                short amt = arg & 0x07;
                short speed = (arg >> 3) & 0x1F;
                if (cur_bfade_amt > 0) { cur_bfade_amt = 0; cur_fade_target = 0; }
                cur_wfade_amt = cur_fade_target;
                cur_fade_target += 0x07F8 * (amt + 1);
                if (cur_fade_target > 0x3FC0) cur_fade_target = 0x3FC0;
                cur_fade_speed = 0x0020 * (speed + 1);
            }
            cur_scene_data_pc += 1;
            goto decideWait;
        case 0x1C:
            cur_async_actions |= ASYNC_PALETTE;
            cur_async_palette_action = APAL_PFADEIN;
            {
                unsigned char arg = *(cur_scene_data + cur_scene_data_pc);
                short amt = arg & 0x07;
                short speed = (arg >> 3) & 0x1F;
                cur_pfade_amt = cur_palette_fade_target;
                cur_palette_fade_target += 0x07F8 * (amt + 1);
                if (cur_palette_fade_target > 0x3FC0) cur_palette_fade_target = 0x3FC0;
                cur_palette_fade_speed = 0x0020 * (speed + 1);
            }
            cur_scene_data_pc += 1;
            goto decideWait;
        case 0x1D:
            cur_async_actions |= ASYNC_PALETTE;
            cur_async_palette_action = APAL_PFADEOUT;
            {
                unsigned char arg = *(cur_scene_data + cur_scene_data_pc);
                short amt = arg & 0x07;
                short speed = (arg >> 3) & 0x1F;
                cur_pfade_amt = cur_palette_fade_target;
                cur_palette_fade_target -= 0x07F8 * (amt + 1);
                if (cur_palette_fade_target < 0) cur_palette_fade_target = 0;
                cur_palette_fade_speed = 0x0020 * (speed + 1);
            }
            cur_scene_data_pc += 1;
            goto decideWait;
        case 0x1E:
            {
                unsigned char arg = *(cur_scene_data + cur_scene_data_pc);
                if (arg == 0)
                {
                    cur_async_actions &= ~ASYNC_FADE;
                    cur_hue_rotation_factor = 0;
                    set_display_palette_out();
                }
                else
                {
                    cur_async_actions |= ASYNC_FADE;
                    cur_async_fade_action = AFADE_PHUEROTATE;
                    cur_hue_rotation_speed = (unsigned short)(arg) * 16;
                }
            }
            cur_scene_data_pc += 1;
            break;
        case 0x1F:
            cur_async_actions |= ASYNC_SCROLL;
            cur_async_scroll_action = ASCR_SHAKE;
            {
                unsigned short arg = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
                unsigned short amp = arg & 0x003F;
                cur_shake_amp = amp << 8;
                unsigned short period = (arg >> 6) & 0x001F;
                cur_shake_adv = (1 << 14) / (period + 1);
                unsigned short damp = (arg >> 11) & 0x001F;
                cur_shake_damp_factor = (1 << 14) - (damp << 6);
                cur_shake_point = 0;
                cur_scene_data_pc += 2;
            }
            decideWait:
            if (*(cur_scene_data + cur_scene_data_pc) == 0x0F) cur_scene_data_pc += 1;
            else control_process(0);
            break;
        case 0x20:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            if (*varptr1 == 0)
            {
                *varptr1 = result;
                cur_scene_data_pc += 4;
                break;
            }
            cur_scene_data_pc += 2;
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            if (*varptr1 == 1) *varptr1 = result;
            else *varptr1 = 0;
            break;
        case 0x21:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            if (*varptr1 == 0) { *varptr1 = result; cur_scene_data_pc += 6; break; }
            cur_scene_data_pc += 2;
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            if (*varptr1 == 1) { *varptr1 = result; cur_scene_data_pc += 4; break; }
            cur_scene_data_pc += 2;
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            if (*varptr1 == 2) *varptr1 = result;
            else *varptr1 = 0;
            break;
        case 0x22:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            if (*varptr1 == 0) { *varptr1 = result; cur_scene_data_pc += 8; break; }
            cur_scene_data_pc += 2;
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            if (*varptr1 == 1) { *varptr1 = result; cur_scene_data_pc += 6; break; }
            cur_scene_data_pc += 2;
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            if (*varptr1 == 2) { *varptr1 = result; cur_scene_data_pc += 4; break; }
            cur_scene_data_pc += 2;
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            if (*varptr1 == 3) *varptr1 = result;
            else *varptr1 = 0;
            break;
        case 0x23:
            result = (vm_flags & VMFLAG_Z) << 1;
            result |= (vm_flags & VMFLAG_N) >> 1;
            vm_flags = (vm_flags & ~(VMFLAG_Z | VMFLAG_N)) | result;
            break;
        case 0x24:
            setvi:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            *varptr1 = result;
            cur_scene_data_pc += 2;
            break;
        case 0x25:
            setvv:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            *varptr1 = *get_variable_ref(result);
            cur_scene_data_pc += 2;
            break;
        case 0x26:
            if (vm_flags & VMFLAG_Z) goto setvi;
            else cur_scene_data_pc += 4;
            break;
        case 0x27:
            if (vm_flags & VMFLAG_Z) goto setvv;
            else cur_scene_data_pc += 4;
            break;
        case 0x28:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            vm_flags &= ~(VMFLAG_Z | VMFLAG_N);
            if (*varptr1 == result) vm_flags |= VMFLAG_Z;
            if (*varptr1 < result) vm_flags |= VMFLAG_N;
            break;
        case 0x29:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            varptr2 = get_variable_ref(result);
            cur_scene_data_pc += 2;
            vm_flags &= ~(VMFLAG_Z | VMFLAG_N);
            if (*varptr1 == *varptr2) vm_flags |= VMFLAG_Z;
            if (*varptr1 < *varptr2) vm_flags |= VMFLAG_N;
            break;
        case 0x2A:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            *varptr1 += result;
            cur_scene_data_pc += 2;
            vm_flags &= ~(VMFLAG_Z | VMFLAG_N);
            if (*varptr1 == 0) vm_flags |= VMFLAG_Z;
            if (*varptr1 < 0) vm_flags |= VMFLAG_N;
            break;
        case 0x2B:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            *varptr1 += *get_variable_ref(result);
            cur_scene_data_pc += 2;
            vm_flags &= ~(VMFLAG_Z | VMFLAG_N);
            if (*varptr1 == 0) vm_flags |= VMFLAG_Z;
            if (*varptr1 < 0) vm_flags |= VMFLAG_N;
            break;
        case 0x2C:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            *varptr1 -= result;
            cur_scene_data_pc += 2;
            vm_flags &= ~(VMFLAG_Z | VMFLAG_N);
            if (*varptr1 == 0) vm_flags |= VMFLAG_Z;
            if (*varptr1 < 0) vm_flags |= VMFLAG_N;
            break;
        case 0x2D:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            varptr1 = get_variable_ref(result);
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            *varptr1 -= *get_variable_ref(result);
            cur_scene_data_pc += 2;
            vm_flags &= ~(VMFLAG_Z | VMFLAG_N);
            if (*varptr1 == 0) vm_flags |= VMFLAG_Z;
            if (*varptr1 < 0) vm_flags |= VMFLAG_N;
            break;
        case 0x2E:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            result = get_flag(result);
            vm_flags &= ~VMFLAG_Z;
            vm_flags |= result;
            break;
        case 0x2F:
            result = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            set_flag(result, vm_flags & VMFLAG_Z);
            break;
        case 0x30:
        {
            unsigned short bgNum = *((unsigned short*)(cur_scene_data + cur_scene_data_pc));
            cur_scene_data_pc += 2;
            ImageInfo* bginf = load_bg_image(bgNum);
            if (!bginf) break;
            bginf->flags |= IMAGE_DRAWREQ;
            redraw_everything();
            break;
        }
        case 0x31: case 0x32: cur_scene_data_pc += 2; break;
        case 0x34: case 0x38: case 0x3C: cur_scene_data_pc += 2; break;
        case 0x35: case 0x39: case 0x3D: cur_scene_data_pc += 2; break;
        case 0x36: case 0x3A: case 0x3E: cur_scene_data_pc += 2; break;
        default: break;
        }
    }
    return return_status;
}
