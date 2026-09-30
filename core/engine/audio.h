/*
 * audio.h — Engine audio manager: MIDI BGM + 86-board PCM (devdoc 101).
 *
 *   audio_init()     open AUDIO.DAT archive, detect MPU-401, log status
 *   audio_tick()     60Hz: advance BGM event cursor + pump PCM FIFO
 *   audio_bgm_*      SMF -> MIDI byte stream scheduling
 *   audio_snd/vc_*   .pcm (8bit mono) streaming on the shared PCM channel
 *   audio_stop_all() scene-end silence (BGM all-notes-off + PCM stop)
 */
#ifndef AUDIO_H
#define AUDIO_H

void audio_init(void);
void audio_tick(void);

void audio_bgm_start(const char *key);
void audio_bgm_stop(void);

void audio_snd_play(const char *key);
void audio_vc_play(const char *key);

void audio_stop_all(void);

/* --- Player switches (devdoc 118) ---
 * State is owned here and applied at the three play entries, so a disabled
 * channel is never decoded or pushed to the hardware.  Disabling a PCM
 * channel cuts only that channel, leaving the other one playing. */
void audio_set_bgm_enabled(int on);
void audio_set_snd_enabled(int on);
void audio_set_vc_enabled(int on);
int  audio_get_bgm_enabled(void);
int  audio_get_snd_enabled(void);
int  audio_get_vc_enabled(void);

/* --- Volume ---
 * BGM: MIDI CC7, 0 (silent) - 127 (loudest), ascending.
 * PCM: A466 attenuation 0 (loudest) - 15 (softest), reversed, shared by
 * snd and voice because they share one PCM path (F02 §4.2). */
void audio_set_bgm_volume(int v);     /* 0-127 */
void audio_set_pcm_volume(int step);  /* 0-15 */
int  audio_get_bgm_volume(void);
int  audio_get_pcm_volume(void);

#endif
