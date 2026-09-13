# Build LaTeX notes to HTML with LaTeXML, then generate navigation index
NOTES_DIR := notes
BUILD_DIR := build/notes
SCRIPT_DIR := scripts

NOTES_TEX := $(wildcard $(NOTES_DIR)/*.tex)
NOTES_HTML := $(patsubst $(NOTES_DIR)/%.tex,$(BUILD_DIR)/%.html,$(NOTES_TEX))

.PHONY: all clean serve spiti-book

all: $(NOTES_HTML) build/index.json spiti-book

# Spiti long read: markdown -> single-page web book (always rebuilt; it's fast)
spiti-book:
	python3 $(SCRIPT_DIR)/build_spiti_book.py

# Use latexmlc (the convenient wrapper running latexml + latexmlpost)
$(BUILD_DIR)/%.html: $(NOTES_DIR)/%.tex
	@mkdir -p $(BUILD_DIR)
	latexmlc --format=html5 --dest=$@ $<

build/index.json: $(NOTES_TEX) $(SCRIPT_DIR)/build_index.py
	@mkdir -p build
	python3 $(SCRIPT_DIR)/build_index.py

clean:
	rm -rf build

serve:
	python3 -m http.server 8000
