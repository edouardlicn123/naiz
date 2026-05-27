OUTPUT_FORMAT("msdos")
OUTPUT_ARCH(i386)
SEARCH_DIR("/opt/gcc-ia16/ia16-elf/lib");
SECTIONS
{
  . = 0x0;
  .text :
  {
    CREATE_OBJECT_SYMBOLS
    *crt0.o(.text)
    *(.text)
    *(.text.*)
    etext = .;
    _etext = .;
    __etext = .;
  }
  .data :
  {
    *(.rodata)
    *(.rodata.*)
    *(.data)
    CONSTRUCTORS
    edata  =  .;
    _edata  =  .;
    __edata  =  .;
  }
  .bss :
  {
    _bss_start = .;
    __bss_start = .;
   *(.bss)
   *(COMMON)
   _bss_end = ALIGN(4);
  }
  . = _bss_end + 0x800;
  _stack_top = .;
  _end = .;
  __end = .;
}
