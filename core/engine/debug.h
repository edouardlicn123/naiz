#ifndef DEBUG_H
#define DEBUG_H

#include "hal.h"

#ifdef NAIZ_DEBUG
    #define NB_DEBUG_ENABLE
#endif

#ifdef NB_DEBUG_ENABLE
    #define NB_DEBUG(...) do { \
        char nb_dbg_buf[256]; \
        snprintf(nb_dbg_buf, sizeof(nb_dbg_buf), __VA_ARGS__); \
        hal_log(nb_dbg_buf); \
    } while(0)
#else
    #define NB_DEBUG(...) ((void)0)
#endif

#endif
