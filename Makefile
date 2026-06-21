# Makefile for generating PMIC register map HTML
# Outputs:
#   dist/json/<pmic>.json   - intermediate JSON from parse_pmic.py
#   dist/regmap/<pmic>.html - final HTML from json2html.py
#   dist/index.html         - index page linking to all regmaps

SHELL = /bin/bash
.DELETE_ON_ERROR:

# Directories
DATA_DIR     := data
ASSET_DIR    := assets
SCRIPT_DIR   := scripts
DIST_DIR     := dist
JSON_DIR     := $(DIST_DIR)/json
REGMAP_DIR   := $(DIST_DIR)/regmap
ASSET_DIST_DIR := $(DIST_DIR)/assets

# Find all PMIC subdirectories that have both required source files
PMICS := $(notdir $(wildcard $(DATA_DIR)/*))
VALID_PMICS := $(foreach pmic,$(PMICS), \
                 $(if $(and $(wildcard $(DATA_DIR)/$(pmic)/upmu_hw.h), \
                            $(wildcard $(DATA_DIR)/$(pmic)/upmu_common.c)), \
                   $(pmic)))

ASSETS := $(notdir $(wildcard $(ASSET_DIR)/*))

# Intermediate JSON files
JSON_TARGETS := $(addprefix $(JSON_DIR)/, $(addsuffix .json, $(VALID_PMICS)))
# Final HTML files
HTML_TARGETS := $(addprefix $(REGMAP_DIR)/, $(addsuffix .html, $(VALID_PMICS)))
# Assets
ASSET_TARGETS := $(addprefix $(ASSET_DIST_DIR)/, $(ASSETS))
# Index page
INDEX_TARGET := $(DIST_DIR)/index.html

# Default target: build all HTML and index
build: $(JSON_TARGETS) $(HTML_TARGETS) $(ASSET_TARGETS) $(INDEX_TARGET)
.PHONY: build

# Ensure output directories exist
$(JSON_DIR) $(REGMAP_DIR) $(ASSET_DIST_DIR) $(DIST_DIR):
	mkdir -p "$@"

# Rule to generate JSON from source files
$(JSON_DIR)/%.json: $(DATA_DIR)/%/upmu_hw.h $(DATA_DIR)/%/upmu_common.c \
                    $(SCRIPT_DIR)/parse_pmic.py | $(JSON_DIR)
	@echo "Generating $@ from $< and $(word 2,$^)"
	$(SCRIPT_DIR)/parse_pmic.py "$<" $(word 2,$^) > "$@"

# Rule to generate HTML from JSON
$(REGMAP_DIR)/%.html: $(JSON_DIR)/%.json $(SCRIPT_DIR)/json2html.py | $(REGMAP_DIR)
	@echo "Generating $@ from $<"
	$(SCRIPT_DIR)/json2html.py "$<" > "$@"

$(ASSET_DIST_DIR)/%: $(ASSET_DIR)/% | $(ASSET_DIST_DIR)
	@echo "Copying asset: $<"
	cp "$<" "$@"

# Generate index.html
# Depends on the list of HTML_TARGETS so it rebuilds if any new PMIC is added/removed
$(INDEX_TARGET): $(HTML_TARGETS) | $(DIST_DIR)
	@echo "Generating $@"
	@echo '<!DOCTYPE html>' > "$@"
	@echo '<html>' >> "$@"
	@echo '<head><meta charset="UTF-8"><title>PMIC Register Maps</title>' >> "$@"
	@echo '<style>' >> "$@"
	@echo 'body { font-family: sans-serif; margin: 20px; background: #f5f5f5; }' >> "$@"
	@echo 'h1 { color: #2c3e50; }' >> "$@"
	@echo 'ul { list-style: none; padding: 0; }' >> "$@"
	@echo 'li { margin: 8px 0; }' >> "$@"
	@echo 'a { text-decoration: none; color: #2980b9; font-size: 1.1em; }' >> "$@"
	@echo 'a:hover { text-decoration: underline; }' >> "$@"
	@echo '</style>' >> "$@"
	@echo '</head><body>' >> "$@"
	@echo '<h1>MediaTek PMIC Register Maps</h1>' >> "$@"
	@echo '<ul>' >> "$@"
	@for pmic in $(VALID_PMICS); do \
		echo '<li><a href="regmap/'$$pmic'.html">'$$pmic'</a></li>' >> "$@"; \
	done
	@echo '</ul>' >> "$@"
	@echo '<p><a href="https://github.com/akku1139/mtk-pmic-datasheet/">Check on GitHub</a></p>' >> "$@"
	@echo '</body></html>' >> "$@"

# Clean: remove all generated files and index
clean:
	rm -rf $(JSON_DIR) $(REGMAP_DIR) $(INDEX_TARGET)
.PHONY: clean

# List detected PMICs
list:
	@echo "Detected PMICs with both required files:"
	@for pmic in $(VALID_PMICS); do echo "  $$pmic"; done
.PHONY: list

preview: build
	python -m http.server -d "$(DIST_DIR)"
.PHONY: preview

# Help
help:
	@echo "Targets:"
	@echo "  build         Build all PMIC register maps + index (default)"
	@echo "  clean         Remove dist/json, dist/regmap, and dist/index.html"
	@echo "  list          Show detected PMIC names"
	@echo "  preview       Build and preview datasheet"
	@echo ""
	@echo "You can also build individual PMICs:"
	@echo "  make dist/regmap/mt6320.html"
.PHONY: help
