/*
 * hal_internal.h — plat/ internal interface (not part of the hal.h public API)
 *
 * Used only by implementation files under plat/; engine code must not include it.
 */
#ifndef HAL_INTERNAL_H
#define HAL_INTERNAL_H

/* Initialise the virtual wall clock (vclock state is private to hal_clock.c);
 * called from hal_init(). */
void hal_clock_init(void);

#endif
