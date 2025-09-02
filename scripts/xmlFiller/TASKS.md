# NSG PDF → XML/JSON Converter - Task Checklist

## Phase 1: Setup & Infrastructure

- [x] Create project directory structure
- [x] Create TASKS.md documentation file
- [x] Create requirements.txt with dependencies
- [x] Set up virtual environment instructions in README.md

## Phase 2: Core Modules

### 2.1 utils.py - Shared Utilities
- [x] Create logging configuration
- [x] Add text normalization helpers (remove umlauts, case-insensitive)
- [x] Add date/time parsing utilities
- [x] Add regex pattern constants
- [x] Add error handling decorators

### 2.2 schema_loader.py - Schema Management
- [x] Load NSGv1.3.json schema
- [x] Build enum registries (dict mapping)
- [x] Create case/umlaut-insensitive lookup functions
- [x] Add enum validation methods
- [x] Create reverse mapping for output

### 2.3 pdf_extractor.py - PDF Text Extraction
- [x] Implement PyMuPDF extraction method
- [x] Implement pdfminer.six fallback method
- [x] Add page-by-page text extraction
- [x] Handle OCR toggle (pytesseract optional)
- [x] Return structured text with page info

### 2.4 text_processor.py - Text Processing
- [x] Detect and remove headers/footers by frequency
- [x] Implement dehyphenation (handle line-break hyphens)
- [x] Normalize whitespace and special characters
- [x] Segment text into paragraphs (§-detection)
- [x] Extract paragraph metadata (nummer, rubrum)

### 2.5 rule_extractor.py - Rule Extraction
- [x] Extract aktivitaet from enum mappings
- [x] Extract ort (location) from enum mappings
- [x] Extract erlaubnis (permission) status
- [x] Parse distance conditions (abstand_m patterns)
- [x] Parse temporal conditions:
  - [x] Date ranges (dd.mm.yyyy format)
  - [x] Seasons (Frühjahr, Sommer, etc.)
  - [x] Time ranges (HH:MM format)
  - [x] Holidays and special events
- [x] Parse quantity conditions:
  - [x] Motor power (kW)
  - [x] Speed limits (km/h)
  - [x] Person limits
  - [x] Material quantities (kg/ha, etc.)
- [x] Parse zone references
- [x] Handle unmapped text (sonstiges/kommentar)

### 2.6 serializer.py - Output Generation
- [x] Build canonical data structure from extracted rules
- [x] Implement XML generation with lxml:
  - [x] Proper attribute ordering
  - [x] Pretty printing
  - [x] Namespace handling
- [x] Implement JSON generation:
  - [x] Ensure UTF-8 encoding
  - [x] Stable key sorting
  - [x] Match XML structure 1:1
- [x] Generate optional report JSON:
  - [x] Coverage statistics
  - [x] Unknown enum counts
  - [x] Processing times

### 2.7 convert.py - Main Entry Point
- [x] Implement argparse CLI interface
- [x] Add argument validation
- [x] Process directory of PDFs
- [x] Orchestrate pipeline:
  - [x] Load schema
  - [x] Load optional synonyms
  - [x] Extract PDF text
  - [x] Process text
  - [x] Extract rules
  - [x] Serialize outputs
- [x] Handle errors gracefully
- [x] Add progress reporting

## Phase 3: Supporting Files

### 3.1 synonyms.json - Mapping Configuration
- [x] Create structure for synonym mappings
- [x] Add common aktivitaet variations
- [x] Add common ort variations
- [x] Add condition type hints
- [x] Document mapping format

### 3.2 README.md - Documentation
- [x] Project description
- [x] Installation instructions
- [x] Virtual environment setup
- [x] CLI usage examples
- [x] Schema format explanation
- [x] Output format description
- [x] Troubleshooting section

## Phase 4: Testing & Validation
- [ ] Test with NSG-7100-001.pdf
- [ ] Test with multiple PDFs batch processing
- [ ] Validate XML output structure
- [ ] Validate JSON output structure
- [ ] Test synonym mapping functionality
- [ ] Test OCR toggle (if tesseract available)
- [ ] Test report generation
- [ ] Verify enum compliance with schema

## Phase 5: Documentation & Polish
- [ ] Add comprehensive code comments
- [ ] Add docstrings to all functions
- [ ] Create example outputs
- [ ] Document known limitations
- [ ] Add error message improvements
- [ ] Final code cleanup

## Implementation Progress

**Current Status**: Implementation complete - ready for testing

**Next Steps**: Test with sample PDFs and validate outputs

---

*Last Updated*: 2025-09-02