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

#endif
