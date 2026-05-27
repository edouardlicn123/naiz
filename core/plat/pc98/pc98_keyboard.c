#include "pc98_keyboard.h"
#include "pc98_gdc.h"

unsigned char prev_key_status[16];
unsigned char key_change_status[16];

void update_prev_key_status(void)
{
    const unsigned int __far* kstat = (const unsigned int __far*)KEY_STATUS;
    unsigned int* pkstat = (unsigned int*)prev_key_status;
    unsigned int* dkstat = (unsigned int*)key_change_status;
    for (int i = 0; i < 8; i++)
    {
        unsigned int ksp = kstat[i];
        dkstat[i] = ksp ^ pkstat[i];
        pkstat[i] = ksp;
    }
}

void wait_vsync(void)
{
    for (;;)
    {
        while (!(gdc_read_gfx_status() & GDC_SYNC_REFRESH)) {}
        while (gdc_read_gfx_status() & GDC_SYNC_REFRESH) {}
    }
}
