# NSG PDF to XML/JSON Converter

A Python tool for converting Naturschutzgebiet (NSG) PDF documents into structured XML and JSON formats following the NSG-Datenmodell v1.3 schema.

## Features

- **Multi-format extraction**: Uses PyMuPDF (primary) and pdfminer.six (fallback) for reliable text extraction
- **Schema-driven**: Strict adherence to NSG v1.3 schema with enum validation
- **Intelligent parsing**: Extracts activities, locations, permissions, and conditions from German legal text
- **Synonym support**: Configurable synonym mappings for better text recognition
- **OCR capability**: Optional OCR support for scanned PDFs (requires Tesseract)
- **Dual output**: Generates both XML and JSON with identical content structure
- **Processing reports**: Optional detailed reports with statistics and coverage metrics

## Installation

### 1. Clone or download the project

```bash
cd /path/to/project
```

### 2. Create and activate virtual environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate (Linux/Mac)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. (Optional) Install OCR support

For scanned PDFs, install Tesseract:

```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr tesseract-ocr-deu

# macOS
brew install tesseract

# Windows
# Download from: https://github.com/UB-Mannheim/tesseract/wiki

# Then uncomment pytesseract in requirements.txt and reinstall
pip install pytesseract
```

## Usage

### Basic conversion

Convert all PDFs in a directory:

```bash
python convert.py --pdf-dir ./pdfs --schema ./schemas/NSGv1.3.json --out ./output
```

### With synonym mappings

Use custom synonym mappings for better recognition:

```bash
python convert.py --pdf-dir ./pdfs --schema ./schemas/NSGv1.3.json \
                  --mapping ./synonyms.json --out ./output
```

### With OCR for scanned PDFs

Enable OCR processing:

```bash
python convert.py --pdf-dir ./pdfs --schema ./schemas/NSGv1.3.json \
                  --out ./output --ocr
```

### Generate processing reports

Create detailed reports for each PDF:

```bash
python convert.py --pdf-dir ./pdfs --schema ./schemas/NSGv1.3.json \
                  --out ./output --report
```

### Verbose logging

Enable detailed logging for debugging:

```bash
python convert.py --pdf-dir ./pdfs --schema ./schemas/NSGv1.3.json \
                  --out ./output --verbose
```

## Command-line Options

| Option | Required | Description |
|--------|----------|-------------|
| `--pdf-dir` | Yes | Directory containing PDF files to convert |
| `--schema` | Yes | Path to NSG schema JSON file (NSGv1.3.json) |
| `--out` | Yes | Output directory for XML and JSON files |
| `--mapping` | No | Path to synonyms mapping JSON file |
| `--ocr` | No | Enable OCR for scanned PDFs |
| `--report` | No | Generate processing report for each PDF |
| `--verbose` | No | Enable verbose logging |
| `--version` | No | Show version information |

## Output Files

For each input PDF `example.pdf`, the converter generates:

- `example.xml` - Structured XML following NSG v1.3 schema
- `example.json` - JSON with identical content structure
- `example.report.json` - Processing report (if `--report` flag used)

### XML Structure Example

```xml
<?xml version='1.0' encoding='UTF-8'?>
<nsg_dokument>
  <schutzgebiet>
    <name>Naturschutzgebiet Example</name>
    <kennung>NSG-7100-001</kennung>
    <datum>01.01.2024</datum>
    <behoerde>Bezirksregierung Example</behoerde>
  </schutzgebiet>
  <regeln>
    <regel>
      <paragraf>3</paragraf>
      <rubrum>Verbote</rubrum>
      <aktivitaet>betreten_abseits_der_wege</aktivitaet>
      <ort>gesamte_flaeche_des_gebietes</ort>
      <erlaubnis>verboten</erlaubnis>
      <bedingungen>
        <bedingung typ="jahreszeit" value="fruehling"/>
        <bedingung typ="datumspanne" date_from="2024-03-01" date_to="2024-06-30"/>
      </bedingungen>
    </regel>
  </regeln>
</nsg_dokument>
```

### JSON Structure Example

```json
{
  "schutzgebiet": {
    "name": "Naturschutzgebiet Example",
    "kennung": "NSG-7100-001",
    "datum": "01.01.2024",
    "behoerde": "Bezirksregierung Example"
  },
  "regeln": [
    {
      "paragraf": "3",
      "rubrum": "Verbote",
      "aktivitaet": "betreten_abseits_der_wege",
      "ort": "gesamte_flaeche_des_gebietes",
      "erlaubnis": "verboten",
      "bedingungen": [
        {
          "typ": "jahreszeit",
          "value": "fruehling"
        },
        {
          "typ": "datumspanne",
          "date_from": "2024-03-01",
          "date_to": "2024-06-30"
        }
      ]
    }
  ]
}
```

## Schema Format

The converter uses the NSG v1.3 schema JSON which defines:

- **Enums**: Controlled vocabularies for activities, locations, permissions, conditions
- **Tables**: Data structure definitions
- **Relationships**: Links between entities

Key enum types:
- `aktivitaet_enum`: Activities (e.g., betreten, radfahren, zelten)
- `ort_enum`: Locations (e.g., uferbereich, ausgewiesene_wege)
- `erlaubnis_enum`: Permissions (erlaubt, verboten, etc.)
- `bedingung_typ_enum`: Condition types (jahreszeit, abstand_m, etc.)

## Synonym Mappings

The `synonyms.json` file allows mapping common variations to standard enum values:

```json
{
  "aktivitaet_synonyms": {
    "Fahrradfahren": "radfahren",
    "Rad fahren": "radfahren"
  },
  "ort_synonyms": {
    "Ufer": "uferbereich",
    "Gewässerufer": "uferbereich"
  }
}
```

## Project Structure

```
nsg-converter/
├── convert.py           # Main entry point
├── schema_loader.py     # Schema and enum management
├── pdf_extractor.py     # PDF text extraction
├── text_processor.py    # Text cleaning and normalization
├── rule_extractor.py    # Rule and condition extraction
├── serializer.py        # XML/JSON output generation
├── utils.py            # Shared utilities
├── requirements.txt     # Python dependencies
├── synonyms.json       # Synonym mappings (optional)
├── README.md           # This file
├── TASKS.md            # Development task checklist
└── schemas/
    └── NSGv1.3.json    # NSG schema definition
```

## Troubleshooting

### No text extracted from PDF

- PDF might be scanned - use `--ocr` flag
- PDF might be corrupted - try opening in PDF reader
- PDF might use unusual encoding - converter will try fallback methods

### Missing enum mappings

- Check if text variations are in `synonyms.json`
- Unmapped values will be marked as "sonstiges" with notes
- Review report files to identify common unmapped patterns

### OCR not working

- Ensure Tesseract is installed: `tesseract --version`
- Install German language data: `tesseract-ocr-deu`
- Check pytesseract is installed: `pip list | grep pytesseract`

### Memory issues with large PDFs

- Process PDFs in smaller batches
- Increase Python memory limit if needed
- Consider splitting large PDFs before processing

## Known Limitations

1. **Language**: Optimized for German legal text
2. **PDF Quality**: Best results with text-based PDFs (not scanned)
3. **Complex Tables**: Table extraction is limited
4. **Multi-column**: May struggle with complex multi-column layouts
5. **Handwritten Text**: Not supported even with OCR

## Development

See `TASKS.md` for detailed development tasks and progress tracking.

To contribute:
1. Check open tasks in TASKS.md
2. Follow existing code structure and style
3. Add tests for new functionality
4. Update documentation as needed

## License

This project is part of the MKUEMRLP NSG documentation system.

## Support

For issues or questions:
- Check existing documentation
- Review error messages and logs
- Enable verbose mode for debugging
- Consult TASKS.md for implementation details

---

Version 1.0.0 - Last updated: 2025-09-02