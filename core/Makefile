CC     = ia16-elf-gcc
AS     = ia16-elf-as
LD     = ia16-elf-ld
CFLAGS = -mcmodel=small -Os -ffreestanding -nostdlib \
         -Wno-pointer-to-int-cast \
         -Iengine -Idata -Iplat -Iplat/pc98 -I.
LDFLAGS = -m i386msdos -e _start --print-memory-usage -T msdos.ld
OUTPUT  = engine.exe

PLAT_OBJS = build/pc98_gdc.o build/pc98_egc.o \
            build/pc98_keyboard.o build/pc98_chargen.o \
            build/memalloc.o build/isr.o \
            build/hal_pc98.o build/lz48086.o

ENGINE_OBJS = build/main.o build/lz4.o build/log.o \
              build/stdbuffer.o build/rootinfo.o build/palette.o \
              build/textengine.o build/graphics.o build/scenevm.o

DATA_OBJS = build/gpimage.o build/fontfile.o build/font_ascii.o

CRT0 = build/crt0.o
OBJS = $(CRT0) $(ENGINE_OBJS) $(DATA_OBJS) $(PLAT_OBJS)

all: $(OUTPUT)

$(OUTPUT): $(OBJS) | build
	$(LD) $(LDFLAGS) -o $@ $(OBJS)

build/crt0.o: crt0.s | build
	$(AS) -o $@ $<

build/%.o: engine/%.c | build
	$(CC) $(CFLAGS) -c -o $@ $<

build/%.o: data/%.c | build
	$(CC) $(CFLAGS) -c -o $@ $<

build/%.o: plat/pc98/%.c | build
	$(CC) $(CFLAGS) -c -o $@ $<

build/%.o: plat/pc98/%.asm | build
	$(AS) -o $@ $<

build:
	mkdir -p build

clean:
	rm -rf build $(OUTPUT)

.PHONY: all clean test

test: $(OUTPUT)
	cp $(OUTPUT) ../games/demo-A1/
	python3 -m tools.naiz_img.inject --game demo-A1 --yes
	../test_hdi.sh demo-A1
