TOOLDIR := ../../tools/mhvn_build
TARGET  := out
BUILD   := obj
SCENESRC := scene
IMAGES   := images
ENGBTEXT := en_GB
JAJPTEXT := ja_JP

SCENEFILES    := $(wildcard $(SCENESRC)/*.sca)
GBENGLISHFILES := $(wildcard $(ENGBTEXT)/*.txt)
JAPANESEFILES  := $(wildcard $(JAJPTEXT)/*.txt)

OBJFILESTXA := EN_GB.otxa JA_JP.otxa
OBJFILESSCX := SCENE.odat
OBJFILESIMG := BGIMAGE.odat SPRITE.odat
OBJFILES    := $(addprefix $(BUILD)/, $(OBJFILESTXA) $(OBJFILESSCX) $(OBJFILESIMG))

.PHONY: all clean

all: $(OBJFILES) | $(TARGET)
	$(TOOLDIR)/mhvnlink -o $(TARGET) -d masterdesc.txt \
	  -s $(BUILD)/SCENE.odat \
	  -t $(BUILD)/EN_GB.otxa -t $(BUILD)/JA_JP.otxa \
	  -bg $(BUILD)/BGIMAGE.odat -spr $(BUILD)/SPRITE.odat \
	  -m $(BUILD)/MUSIC.odat -sfx $(BUILD)/SOUNDFX.odat \
	  -sys $(BUILD)/SYSTEM.odat

$(BUILD)/SCENE.odat: $(SCENEFILES) | $(BUILD)
	$(TOOLDIR)/mhvnscas -o $@ $^

$(BUILD)/BGIMAGE.odat: $(IMAGES)/bglist.txt | $(BUILD)
	$(TOOLDIR)/mhvnimgp -o $@ -b $^

$(BUILD)/SPRITE.odat: $(IMAGES)/sprlist.txt | $(BUILD)
	$(TOOLDIR)/mhvnimgp -o $@ -s $^

$(BUILD)/EN_GB.otxa: $(GBENGLISHFILES) | $(BUILD)
	$(TOOLDIR)/mhvntxar -o $@ $^

$(BUILD)/JA_JP.otxa: $(JAPANESEFILES) | $(BUILD)
	$(TOOLDIR)/mhvntxar -o $@ $^

$(BUILD) $(TARGET):
	mkdir -p $@

clean:
	rm -rf $(BUILD) $(TARGET)
