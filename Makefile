# Makefile for generating PMIC register map HTML
# Outputs:
#   dist/json/<pmic>.json   - intermediate JSON from parse_pmic.py
#   dist/regmap/<pmic>.html - final HTML from json2html.py

SHELL = /bin/bash
.DELETE_ON_ERROR:

# Directories
DATA_DIR     := data
SCRIPT_DIR   := scripts
DIST_DIR     := dist
JSON_DIR     := $(DIST_DIR)/json
REGMAP_DIR   := $(DIST_DIR)/regmap

# Find all PMIC subdirectories that have both required source files
PMICS := $(notdir $(wildcard $(DATA_DIR)/*))
VALID_PMICS := $(foreach pmic,$(PMICS), \
                 $(if $(and $(wildcard $(DATA_DIR)/$(pmic)/upmu_hw.h), \
                            $(wildcard $(DATA_DIR)/$(pmic)/upmu_common.c)), \
                   $(pmic)))

# Intermediate JSON files
JSON_TARGETS := $(addprefix $(JSON_DIR)/, $(addsuffix .json, $(VALID_PMICS)))
# Final HTML files
HTML_TARGETS := $(addprefix $(REGMAP_DIR)/, $(addsuffix .html, $(VALID_PMICS)))

# Default target: build all HTML files
all: $(HTML_TARGETS)
.PHONY: all

# Ensure output directories exist
$(JSON_DIR) $(REGMAP_DIR):
	mkdir -p $@

# Rule to generate JSON from source files
# Depends on both .c and .h and the parsing script
$(JSON_DIR)/%.json: $(DATA_DIR)/%/upmu_hw.h $(DATA_DIR)/%/upmu_common.c \
                    $(SCRIPT_DIR)/parse_pmic.py | $(JSON_DIR)
	@echo "Generating $@ from $< and $(word 2,$^)"
	$(SCRIPT_DIR)/parse_pmic.py $(DATA_DIR)/$*/upmu_hw.h $(DATA_DIR)/$*/upmu_common.c > $@

# Rule to generate HTML from JSON
$(REGMAP_DIR)/%.html: $(JSON_DIR)/%.json $(SCRIPT_DIR)/json2html.py | $(REGMAP_DIR)
	@echo "Generating $@ from $<"
	$(SCRIPT_DIR)/json2html.py $< > $@

# Clean: remove all generated files
clean:
	rm -rf $(JSON_DIR) $(REGMAP_DIR)
.PHONY: clean

# List detected PMICs
list:
	@echo "Detected PMICs with both required files:"
	@for pmic in $(VALID_PMICS); do echo "  $$pmic"; done
.PHONY: list

# Help
help:
	@echo "Targets:"
	@echo "  all           Build all PMIC register maps (default)"
	@echo "  clean         Remove dist/json and dist/regmap"
	@echo "  list          Show detected PMIC names"
	@echo ""
	@echo "You can also build individual PMICs:"
	@echo "  make dist/regmap/mt6320.html"
.PHONY: help
