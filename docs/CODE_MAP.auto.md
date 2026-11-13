# CODE_MAP（自动生成，勿手改）

> 生成命令：`python -m tools.diag.code_map`；校验：`--check`；定位：`--find <前缀或正则>`
> 只列公共符号与职责，不含行号——需要行号用 `--find`。

## core/engine/

| 文件 | 职责 | 公共符号 | 相关规范 |
|---|---|---|---|
| audio.c | Engine audio manager: MIDI BGM scheduling + 86-board PCM pump. | audio_bgm_start, audio_bgm_stop, audio_snd_play, audio_vc_play, audio_set_bgm_enabled, audio_set_snd_enabled, audio_set_vc_enabled, audio_get_bgm_enabled, audio_get_snd_enabled, audio_get_vc_enabled, audio_set_bgm_volume, audio_set_pcm_volume, audio_get_bgm_volume, audio_get_pcm_volume, audio_pump_once, audio_init, audio_tick_isr, audio_tick_isr_pending, audio_tick, audio_stop_all, audio_preload_bgm (21) | B19-时钟计算经验参考.md |
| bootmenu.c | Pre-game boot menu (C-code rendered): Language + Start Game. | bootmenu_run (1) | - |
| cursor.c | Software cursor shape drawing, background save/restore and | cursor_render, cursor_render_force, cursor_erase_current, cursor_invalidate, cursor_touch, cursor_touch_opaque, cursor_composite_splice, cursor_refresh (8) | B13-鼠标直连方案.md |
| frame.c | Unified per-frame heartbeat (devdoc 129). | engine_frame_pump, frame_decode_pump (2) | B97-场景过渡状态机规范.md |
| image.c | on-demand archive reader (devdoc 100). | image_init, image_load, image_prefetch, image_raw_blob (4) | B11-MAG图片加载与显示规范.md |
| image_cache.c | LRU cache for decoded MAG images. | image_cache_init, image_cache_clear, image_cache_lookup, image_cache_insert, image_cache_pin (5) | B98-图片缓存槽规范.md |
| input_boundary.c | User-input discard at script boundaries. | input_drain_boundary (1) | - |
| layer.c | cross-layer lifecycle. | scene_end, layer_is_active, layer_set_active (3) | B15-图层渲染与换装机制.md |
| layer_bg.c | captured from the source image (never VRAM | layer_bg_restore_rect, layer_capture_bg_dialog_from_image, layer_bg_reset, layer_bg_snapshot, layer_bg_under_dialog, layer_bg_change (6) | B11-MAG图片加载与显示规范.md |
| layer_debug.c | Visual debugging: PPM export for layer diagnostics. | layer_debug_handle (1) | B12-VRAM渲染策略：两趟叠加与局部刷新.md |
| layer_dialog.c | part of the scene layer subsystem. | dlg_update_palette, btn_update_palette, dlg_set_style, dlg_get_style, btn_set_style, fill_dialog_bg, dialog_occluder_reset_base, layer_dialog_occluder, dialog_layer_blit, layer_dialog_show, layer_dialog_clear, layer_dialog_render_page, dialog_layer_store_render, layer_dialog_hide, layer_dialog_drawn, layer_dialog_recompose, layer_dialog_reset, layer_dialog_snapshot (18) | B02-显示管线规范.md |
| layer_sprite.c | part of the scene layer subsystem. | layer_sprite_sync_dialog_base, layer_sprite_face, layer_sprite_hide_all_ex, layer_sprite_hide_all, layer_has_sprite, layer_redraw_sprites, layer_sprite_update (7) | B15-图层渲染与换装机制.md |
| main.c | HAL / 字库 / 键盘 / 视频 / 调色板 / 图片归档初始化 | main (1) | B01-Engine日志机制.md |
| menu_layer.c | reusable menu overlay layer (draw / blit / restore). | menu_layer_open, menu_layer_begin_draw, menu_layer_commit, menu_layer_blit, menu_layer_blit_rect, menu_layer_erase_to_base, menu_layer_blit_sprite, menu_layer_close (8) | B15-图层渲染与换装机制.md |
| nb.c | pure-text script engine for Naiz | nb_get_last_brace_arg, nb_set_scene_conf, nb_set_last_choice, nb_get_buffer, nb_lang_is_cjk, nb_init, nb_get_playback_mode, scene_switch, nb_is_menu_scene, nb_get_state, nb_set_lang, nb_seek_tag, nb_scene_switch_tagged, nb_preload_scene, nb_prefetch_lookahead, nb_process (16) | B02-显示管线规范.md |
| nb_anim.c | nb_anim.c | cmd_playanima, cmd_waitanima, cmd_stopanima, anim_waiting, anim_stop, anim_tick (6) | B19-时钟计算经验参考.md |
| nb_audio.c | NB audio commands (bgm/sound/voice). | cmd_bgm, cmd_sound, cmd_voice (3) | B92-NB脚本命令参考.md |
| nb_cg.c | nb_cg.c | cmd_cg (1) | B92-NB脚本命令参考.md |
| nb_cggallery.c | NB CG gallery grid menu. | cmd_cgvmenu (1) | B92-NB脚本命令参考.md |
| nb_commands.c | NB script command handlers and dispatch table | nb_asset_id, nb_prefetch_key, nb_next_field, nb_has_field_delim, nb_commands_dispatch (5) | B11-MAG图片加载与显示规范.md |
| nb_dialog.c | Dialog paging state machine for NB script engine. | nb_text_expand_vars, dialog_show, nb_dialog_get_text, nb_dialog_get_offset, nb_dialog_get_charname, nb_dialog_pending, nb_dialog_reveal_tick, nb_dialog_reveal_active, nb_dialog_reveal_finish, nb_dialog_dismiss, nb_dialog_reset (11) | B02-显示管线规范.md |
| nb_interact.c | blocking option-list interaction primitive (ui_interact). | ui_interact (1) | - |
| nb_mainmenu.c | NB main-menu flow commands. | nb_set_menu_return, nb_get_menu_return, cmd_mainmenu, cmd_startsetting (4) | B92-NB脚本命令参考.md |
| nb_menu.c | NB menu UI: button rendering, palette save/restore, input loop. | menu_save_item_palette, menu_restore_item_palette, menu_finish, menu_pagecount, menu_pagenav_draw, menu_page_hit, menu_back_draw, menu_back_hit, menu_confirm_input, menu_consume_key, menu_show (11) | B18-存档读档系统设计.md |
| nb_music.c | Music Room (LOAD-paradigm full-screen list). | cmd_musicmenu (1) | - |
| nb_nameinput.c | Name-entry page (NB command `nameinput`, devdoc 205). | cmd_nameinput (1) | B92-NB脚本命令参考.md |
| nb_parser.c | NB script line parser (tokenizer). | nb_parse_line, nb_get_line, nb_parse_line_semi (3) | B96-NB解析器规范.md |
| nb_question.c | NB question/choice command (cmd_question) and helpers. | nb_prompt_options, cmd_question (2) | B92-NB脚本命令参考.md |
| nb_save_dialog.c | In-dialog save menu. | save_dialog_menu (1) | B18-存档读档系统设计.md |
| nb_saveload.c | Save/load menu UIs (full-screen + in-dialog). | slot_chapter_label, cmd_loadscene, save_request (3) | B18-存档读档系统设计.md |
| nb_scene.c | NB scene-jump command (cmd_scene) and its helpers. | cmd_scene, cmd_jump, cmd_jumpscene (3) | B92-NB脚本命令参考.md |
| nb_scene_menu.c | Scene select menu (scene gallery). | cmd_scenesmenu (1) | B92-NB脚本命令参考.md |
| nb_setting.c | In-game settings scene (LOAD-paradigm full-screen list). | cmd_settingmenu (1) | B92-NB脚本命令参考.md |
| nb_special.c | Special menu (LOAD-style full-screen list). | cmd_specialmenu (1) | B92-NB脚本命令参考.md |
| nb_vars.c | nb_vars.c | nb_var_init, nb_var_get, nb_var_set, nb_var_add, nb_var_lookup, nb_var_get_str, nb_var_set_str, nb_var_default_str, nb_var_get_state, nb_var_set_state, char, nb_var_set_str_state (12) | B17-变量系统设计规范.md |
| palette.c | Palette read/write/interpolate primitives. | palette_get_all, palette_set_all, palette_interp, palette_reset_reserved, palette_apply_dirty_rgb, palette_apply_dirty_pal (6) | - |
| prefs.c | Player preferences (USER.CFG) parser. | prefs_get_version, prefs_get_blackletter_title, prefs_get_blackletter_dialog, prefs_get_lang, prefs_get_text_speed, prefs_get_bgm_enabled, prefs_get_snd_enabled, prefs_get_vc_enabled, prefs_get_bgm_volume, prefs_get_pcm_volume, prefs_set_text_speed, prefs_set_bgm_enabled, prefs_set_snd_enabled, prefs_set_vc_enabled, prefs_set_bgm_volume, prefs_set_pcm_volume, prefs_load, prefs_save, prefs_set_lang (19) | - |
| preload_queue.c | see preload_queue.h (devdoc 177 Phase 3). | preload_queue_init, preload_push, preload_cancel, preload_pending, preload_step (5) | - |
| render.c | 256-color Packed-Pixel via PEGC bank switching. | render_set_target, render_set_target_vram, vram_pset_addr, fill_rect, fill_diag_sweep, draw_rect, fill_rect_pattern, vblank_wait (8) | B02-显示管线规范.md |
| render_blit.c | VRAM sprite/background blits with transparency, mirror | vram_blit, vram_blit_sprite (2) | - |
| render_text.c | ASCII/CJK glyph drawing to VRAM. | text_set_target, text_set_target_vram, text_set_blackletter, draw_text, text_width, draw_title_large, text_title_width (7) | B02-显示管线规范.md |
| render_vram.c | rectangular read/write between the banked VRAM window | vram_read, vram_write, render_blit_transparent (3) | B15-图层渲染与换装机制.md |
| save.c | save.c | save_get_filename, save_game_temp, save_game_slot, load_game_temp, load_game_slot, slot_info (6) | B18-存档读档系统设计.md |
| save_io.c | Shared save-file I/O helpers for save.c and save_sys.c. | save_file_write, save_file_read, save_read_header (3) | B18-存档读档系统设计.md |
| save_sys.c | System save (CG/ending/scene unlock flags, clear count). | sys_save_load, sys_save_unlock_scene, sys_save_is_scene_unlocked, sys_save_unlock_cg, sys_save_is_cg_unlocked (5) | B18-存档读档系统设计.md |
| scene_display.c | Display-side scene state: narrow apply facade. | display_apply_bg, display_apply_cg, display_apply_sprite, display_apply_dialog (4) | - |
| transition.c | Scene transition dispatcher. | transition_start, transition_active, transition_sweeping, transition_tick (4) | B95-VM执行核心规范.md |
| transition_blinds.c | Blinds (strip sweep) transition family. | transition_pblinds_wipe (1) | B97-场景过渡状态机规范.md |
| transition_checker.c | Checkered staggered wipe transition. | transition_checker_wipe (1) | B97-场景过渡状态机规范.md |
| transition_pfade.c | Palette fade transition family. | transition_pfade_solid (1) | B97-场景过渡状态机规范.md |
| ui.c | UI rendering primitives (rounded rects, emboss, title text). | draw_rounded_emboss_outline, draw_rounded_emboss (2) | B93-图层渲染与菜单图层规范.md |
| vm.c | VM runtime state ownership for the NB script engine. | vm_request_process, vm_set_error, vm_set_finalend, vm_request_scene_change, vm_clear_scene_change, vm_pause_process, vm_clear_error, vm_get_flags, vm_delay_reset, vm_set_delay, vm_delay_tick, vm_delay_active (12) | B95-VM执行核心规范.md |

## core/lib/

| 文件 | 职责 | 公共符号 | 相关规范 |
|---|---|---|---|
| cjk.c | CJK 16×16 点阵字形加载器 | cjk_init, cjk_load_for_lang, cjk_get_glyph (3) | B03-HAL接口规范.md |
| farchive.c | On-demand reader for TOC-archived game files. | farchive_set_progress_hook, farchive_open, farchive_close, farchive_lookup_id, farchive_lookup_name, farchive_read_alloc, farchive_read_buf (7) | B92-NB脚本命令参考.md |
| fmopn.c | Pure OPNA register model: note/time encoders + register | fmopn_ratio_freq_x256, fmopn_note_ratio, fmopn_bend_ratio, fmopn_keyon_value, fmopn_ssg_period_fine, fmopn_ssg_period_coarse, fmopn_op_addr, fmopn_ch_addr (8) | - |
| fmopn_patch.c | OPNA patch-record model (devdocs/123 §四 M1, §五; F03 §5.2). | fmopn_patch_validate, fmopn_patch_fb_alg, fmopn_patch_pan, fmopn_patch_ams, fmopn_patch_pms, fmopn_op_dt_mul, fmopn_op_tl, fmopn_op_ks_ar, fmopn_op_am_d1r, fmopn_op_d2r, fmopn_op_sl_rr (11) | - |
| fmseq.c | MIDI -> OPNA voice allocator (devdocs/123 §四 M2). | fmseq_size, fmseq_init, fmseq_events, fmseq_pump, fmseq_stop, fmseq_fm_voices, fmseq_finished (7) | - |
| font.c | ASCII 8×16 点阵字形加载器 | font_init, font_get_glyph, font_load_alt, font_get_glyph_alt (4) | B02-显示管线规范.md |
| mag.c | PC-98 dominant image format. | hal_wallclock_ms, mag_set_progress_hook, mag_decode, mag_read_palette, mag_release, mag_retain, mag_decode_into (7) | B03-HAL接口规范.md |
| midi.c | Minimal SMF (Standard MIDI File) parser. | midi_parse, midi_free (2) | - |
| naiz_file.c | Shared file I/O helpers. | file_read_all (1) | B03-HAL接口规范.md |
| strutil.c | Bounded string helpers. | str_copy, utf8_len_cps, utf8_cp_len, utf8_truncate_cps, str_toc8 (5) | - |
| tr.c | 运行时翻译表（i18n） | tr_init, tr, tr_get_count, tr_get_truncations (4) | B03-HAL接口规范.md |
| vclock.c | Smoothed virtual clock (devdoc 129/133). | vclock_init, vclock_advance, vclock_ms, vclock_advance_fixed (4) | B03-HAL接口规范.md |

## core/plat/

| 文件 | 职责 | 公共符号 | 相关规范 |
|---|---|---|---|
| gdc.c | GDC（μPD7220）256 色 PEGC 调色板接口 | gdc_set_palette, gdc_read_palette (2) | B02-显示管线规范.md |
| hal_audio.c | PC-98 audio HAL: MPU-401 (MIDI) + 86-board PCM (devdoc 101). | hal_audio_detect, hal_midi_out, hal_pcm_active, hal_pcm_set_volume, hal_pcm_play, hal_pcm_stop, hal_pcm_advance_units (7) | - |
| hal_clock.c | HAL PC-98 wall clock and vertical-sync implementation | hal_clock_init, hal_wallclock_ms, hal_wallclock_smooth_ms, hal_wallclock_smooth_advance, hal_wallclock_fixed_advance, hal_wallclock_last_advance_units, hal_vblank_wait, hal_vblank_poll (8) | B03-HAL接口规范.md |
| hal_fm.c | 86-board OPNA FM register interface (devdocs/123 M3, F03 §3.8). | hal_fm_detect, hal_fm_init, hal_fm_set_volume, hal_fm_shutdown, hal_fm_write_reg (5) | - |
| hal_irq.c | Interrupt-driven BGM pump (devdoc 164 phase 1, OPNA Timer-B). | hal_bgm_irq_in_isr, hal_bgm_irq_init, hal_bgm_irq_active, hal_bgm_irq_ticks, hal_bgm_irq_take_pending_units, hal_bgm_irq_set_on, hal_bgm_irq_is_on, hal_bgm_irq_probe_step, hal_bgm_irq_shutdown, hal_bgm_irq_take_pending_units (10) | B03-HAL接口规范.md |
| hal_log.c | HAL PC-98 debug logging | hal_log, hal_logf (2) | B03-HAL接口规范.md |
| hal_pc98.c | HAL PC-98 platform implementation (init / palette / VRAM) | hal_init, hal_set_palette, hal_read_palette, hal_vram_bank_select, hal_vram_get_window (5) | B02-显示管线规范.md |
| hal_probe.c | HAL PC-98 interrupt-capability probes | hal_irq_probe_run, hal_dpmi_probe_run (2) | B03-HAL接口规范.md |
| keyboard.c | PC-98 键盘输入驱动 | hal_kbd_set_ignore_frames, hal_kbd_init, hal_kbd_update, hal_kbd_get_char, hal_kbd_is_down, hal_kbd_flush, hal_kbd_wait_any, hal_kbd_drain_advance (8) | B03-HAL接口规范.md |
| mouse.c | mouse.c | hal_mouse_init, hal_mouse_update, hal_mouse_get_x, hal_mouse_get_y, hal_mouse_available, hal_mouse_get_display_x, hal_mouse_get_display_y, hal_mouse_was_clicked, hal_mouse_flush, hal_mouse_drain, hal_mouse_recenter_if_idle, hal_mouse_set_pos, hal_mouse_invalidate_cursor, hal_mouse_erase_cursor, hal_mouse_draw_cursor, hal_mouse_draw_cursor_force, hal_mouse_touch_cursor, hal_mouse_touch_cursor_opaque (18) | B03-HAL接口规范.md |
| serial.c | uPD8251 串口驱动（COM1, 9600 8N1） | serial_init, serial_puts (2) | - |
| video.c | CRT BIOS 显示通道（INT 18h）与 PEGC 初始化 | hal_video_init, hal_video_check_palette, hal_video_exit (3) | B02-显示管线规范.md |
| vram.c | GDC VRAM 的 DPMI 线性地址映射 (NOT COMPILED by default) | vram_init, vram_plane (2) | B09-引擎开发与调试全流程.md |

