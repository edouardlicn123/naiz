# Makefile for fmbench — offline YM2608 FM render oracle (devdocs/136 P1a).
#
# Host-only developer tool.  Compiles fmbench.cpp together with the vendored
# ymfm YM2608 core.  Requires a C++14 compiler (g++ or clang++).
#
#   make          build ./fmbench
#   make clean    remove build artefacts

CXX      ?= g++
CXXFLAGS ?= -std=c++14 -O2 -Wall -Wextra
# Vendored third-party sources: build quietly (their own -Wextra noise is not ours).
VENDOR_CXXFLAGS ?= -std=c++14 -O2 -w
LDLIBS   ?= -lm

VENDOR   := ../../vendor/ymfm/src
YM_SRCS  := ymfm_misc.cpp ymfm_opl.cpp ymfm_opm.cpp ymfm_opn.cpp \
            ymfm_adpcm.cpp ymfm_pcm.cpp ymfm_ssg.cpp
YM_OBJS  := $(YM_SRCS:.cpp=.o)

BIN      := fmbench

.PHONY: all clean
all: $(BIN)

$(BIN): fmbench.o $(YM_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

fmbench.o: fmbench.cpp
	$(CXX) $(CXXFLAGS) -isystem $(VENDOR) -c -o $@ $<

%.o: $(VENDOR)/%.cpp
	$(CXX) $(VENDOR_CXXFLAGS) -I$(VENDOR) -c -o $@ $<

clean:
	rm -f $(BIN) *.o
