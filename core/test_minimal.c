void _start(void)
{
    __asm volatile (
        "mov $'A', %%al\n\t"
        "movb $0x00, %%ah\n\t"
        "int $0x18\n\t"
        "mov $0x4C00, %%ax\n\t"
        "int $0x21\n\t"
        : : : "%ax");
}
