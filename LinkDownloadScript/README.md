# PDF Download Script for Naturschutzgebiete

A Python script to download PDF files from links extracted from Excel files containing Naturschutzgebiete data.

## Features

- Extracts PDF URLs from HTML anchor tags in Excel files
- Downloads ~500 PDFs with progress tracking
- Creates organized folder structure
- Handles errors and skips existing files
- Command-line interface

## Requirements

- Python 3.6+
- Dependencies listed in `requirements.txt`

## Installation

1. Install required packages:
```bash
pip install -r requirements.txt
```

## Usage

```bash
python download_pdfs.py <excel_file_path>
```

### Example
```bash
python download_pdfs.py data.xlsx
```

## Excel File Format

The script expects an Excel file with a column named `Rechtsverordnung` containing HTML anchor tags like:

```html
<a href="http://www.naturschutz.rlp.de/Dokumente/rvo/nsg/NSG-7100-001.pdf" target="_blank">» Link</a>
```

## Output

- Downloads PDFs to: `Rechtsverordnungen Naturschutzgebiete/`
- Displays progress bar during downloads
- Shows summary: downloaded, skipped, failed counts
- Skips files that already exist

## Error Handling

- Validates Excel file existence and format
- Handles network timeouts and HTTP errors
- Reports failed downloads with error messages
- Continues downloading remaining files on individual failures