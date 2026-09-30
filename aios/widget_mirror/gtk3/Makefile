# Widget Mirror GTK3 module
CC ?= gcc
CFLAGS ?= -fPIC -O2 -Wall $(shell pkg-config --cflags gtk+-3.0 2>/dev/null)
LDFLAGS ?= -shared $(shell pkg-config --libs gtk+-3.0 2>/dev/null) -lrt

all: libaios-mirror.so

libaios-mirror.so: aios_mirror.c
	@if pkg-config --exists gtk+-3.0; then \
	  $(CC) $(CFLAGS) -o $@ $< $(LDFLAGS); \
	  echo "built $@"; \
	else \
	  echo "SKIP: gtk+-3.0 not installed (apt install libgtk-3-dev)"; \
	fi

clean:
	rm -f libaios-mirror.so

install: libaios-mirror.so
	install -d $(DESTDIR)/usr/lib/gtk-3.0/modules
	install -m 644 libaios-mirror.so $(DESTDIR)/usr/lib/gtk-3.0/modules/libaios-mirror.so

.PHONY: all clean install
