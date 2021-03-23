CSSURL ?= mandoc.css
DESTDIR ?= $(CURDIR)

MANPAGES = chaqum.1
FILES = mandoc.css

all: $(patsubst %,$(DESTDIR)/%.html,$(MANPAGES))
ifneq ($(realpath $(DESTDIR)), $(realpath $(CURDIR)))
all: $(patsubst %,$(DESTDIR)/%,$(FILES))
endif

$(DESTDIR)/%.html : % $(DESTDIR)
	mandoc \
	    -mdoc -T html \
	    -O man=%N.%S.html,style=$(CSSURL) \
	    $< > $@

$(DESTDIR)/% : % $(DESTDIR)
	cp $< $@

$(DESTDIR):
	mkdir -p $(DESTDIR)
