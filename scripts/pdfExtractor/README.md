# NSG Enum-Diff Tool (nsgx)

A minimal, fast Python CLI tool for identifying missing enum values from German Nature Reserve Regulations (NSG) PDFs using DeepSeek API for intelligent content analysis.

## 🚀 Quick Start

```bash
# Setup (one-time)
./setup.sh
source venv/bin/activate
cp .env.example .env
# Edit .env with your DeepSeek API key

# Run enum-diff on your PDFs
nsgx enumdiff --pdfdir ./data/pdfs --concurrency 6 --provider-mode auto
```

**That's it!** The tool identifies missing enum values for `aktivitaet_enum`, `zone_typ_enum`, and `ort_enum` in minutes, not hours.

## Features

- **⚡ Minimal & Fast**: Direct PDF → enum-diff workflow, no intermediate steps
- **🎯 Conservative Analysis**: Anti-explosion policy prevents enum proliferation
- **🧠 Adaptive Intelligence**: Chat model by default, escalates to reasoner when uncertain
- **💾 Smart Caching**: SQLite cache prevents redundant API calls
- **📊 Clear Outputs**: Review CSV, DBML patches, and changelog

## Installation

### Automated Setup (Recommended)

```bash
# Clone or download the project
cd pdfExtractor

# Run the setup script (creates virtual environment and installs dependencies)
./setup.sh

# Activate the virtual environment
source venv/bin/activate

# Edit the .env file with your API credentials
nano .env
```

### Manual Installation

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
cp .env.example .env
nano .env  # Edit with your DeepSeek API credentials
```

## Configuration

### Environment Variables (.env file)

```bash
# Required
DEEPSEEK_ENDPOINT=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_API_KEY=sk-your-api-key-here

# Optional (auto-detected if not set)
DEEPSEEK_MODEL_CHAT=deepseek-chat
DEEPSEEK_MODEL_REASONER=deepseek-reasoner
```

## Usage

### Basic Command

```bash
nsgx enumdiff --pdfdir ./data/pdfs
```

### Full Options

```bash
nsgx enumdiff \
  --pdfdir ./data/pdfs \
  --out ./out/enumdiff \
  --provider-mode auto \
  --concurrency 6 \
  --min-doc-count 5 \
  --force
```

### Options Explained

- `--pdfdir`: Directory containing PDF files (searched recursively)
- `--out`: Output directory (default: `./out/enumdiff`)
- `--provider-mode`:
  - `chat`: Fast mode using chat model only
  - `reasoner`: Thorough mode using reasoner model only
  - `auto`: Smart mode - chat by default, escalates to reasoner when uncertain
- `--concurrency`: Number of concurrent API requests (default: 4)
- `--min-doc-count`: Minimum documents a candidate must appear in (default: 5)
- `--force`: Overwrite existing outputs

## How It Works

### 1. **Smart Paragraph Filtering**

Extracts only rule-bearing paragraphs containing:

- `verboten|untersagt|zulässig|Ausnahme|Genehmigung|Befreiung|Ordnungswidrigkeit|§ [34]`
- Skips preambles, signatures, annexes

### 2. **Conservative Enum Analysis**

Uses DeepSeek API with anti-explosion rules:

- Maps qualifiers (engine power, group size, seasons) to conditions, not new enums
- Prefers mapping to existing enums over creating new ones
- Requires evidence (citations) for all proposals

### 3. **Adaptive Processing**

- **Chat model**: Fast analysis for clear cases
- **Reasoner model**: Deep analysis when uncertain (confidence < 0.65 or decision = UNSURE)
- **Caching**: SQLite cache prevents reprocessing

### 4. **Aggregation & Thresholds**

- Clusters similar candidates using fuzzy matching (80% similarity)
- Applies minimum document count threshold
- Generates clean outputs for review

## Output Structure

```
out/enumdiff/
├── proposals.jsonl              # Per-paragraph API responses
├── cache.sqlite                 # API response cache
├── review/
│   └── candidates_review.csv    # Detailed candidate analysis
├── dbml_patches/
│   └── enum_additions.dbml      # DBML patches for new enum values
├── CHANGELOG.md                 # Summary of new terms and definitions
└── enumdiff_summary.json        # Processing statistics
```

### Review CSV Columns

| Column           | Description                                   |
| ---------------- | --------------------------------------------- |
| `type`           | Enum type (aktivitaet, zone, ort)             |
| `candidate`      | Proposed enum value                           |
| `decision`       | ADD_NEW, MAP_TO_EXISTING, IGNORE, UNSURE      |
| `target_or_key`  | Existing enum to map to (if MAP_TO_EXISTING)  |
| `reason`         | Justification for the decision                |
| `doc_count`      | Number of documents containing this candidate |
| `example_quote`  | Best citation/quote example                   |
| `confidence_avg` | Average confidence score                      |

## Configuration Files

### `prompts/known_enums.json`

Contains the canonical enum lists that mirror your current DBML data model. Update this file when your data model changes to ensure accurate mapping.

### `prompts/enumdiff_system.txt`

The system prompt used for DeepSeek API analysis. The placeholder `{{KNOWN_ENUMS_JSON}}` is automatically replaced with the contents of `known_enums.json` at runtime.

## Integration with Your Data Model

1. **Review**: Check `review/candidates_review.csv` to validate proposed additions
2. **Context**: Read `CHANGELOG.md` for definitions and examples
3. **Apply**: Use `dbml_patches/enum_additions.dbml` to update your DBML schema
4. **Update**: Modify `prompts/known_enums.json` to reflect the new model
5. **Code**: Update your application code to handle new enum values

## Performance & Cost

- **Speed**: ~100 PDFs processed in 5-10 minutes (chat mode)
- **Cost**: ~$2-5 USD for 1000 pages with DeepSeek pricing
- **Efficiency**: 80% fewer API calls vs. full rule extraction

## Example Workflow

```bash
# 1. Setup project
./setup.sh
source venv/bin/activate

# 2. Configure API credentials
cp .env.example .env
nano .env  # Add your DeepSeek API key

# 3. Place your PDFs
mkdir -p data/pdfs
# ... copy PDF files ...

# 4. Run enum-diff analysis
nsgx enumdiff --pdfdir data/pdfs --concurrency 6 --provider-mode auto

# 5. Review results
head -20 out/enumdiff/review/candidates_review.csv
cat out/enumdiff/CHANGELOG.md
cat out/enumdiff/dbml_patches/enum_additions.dbml

# 6. Apply to your data model
# ... integrate DBML patches into your schema ...
```

## Error Handling & Troubleshooting

### Common Issues

#### PDF Extraction

- Ensure `pdftotext` is installed for fallback extraction
- Check PDF file permissions and integrity
- Review `logs/enumdiff.log` for specific extraction failures

#### API Issues

- Verify environment variables are set correctly
- Check API key permissions and rate limits
- Reduce `--concurrency` if hitting rate limits

#### DeepSeek-Specific Issues

- **Empty responses**: Tool includes automatic retry logic for this known issue
- **JSON mode errors**: Fixed automatically by ensuring prompts contain "json" keyword
- **Rate limiting**: Automatic backoff and retry with exponential delays

#### Memory Issues

- Process documents in smaller batches
- Check available disk space for output files
- Reduce `--concurrency` for memory-constrained environments

## Dependencies

Core dependencies (automatically installed):

- `click`: CLI framework
- `pdfminer.six`: Primary PDF extraction
- `pypdf`: Fallback PDF extraction  
- `requests`: HTTP client for API calls
- `rapidfuzz`: String similarity matching
- `python-dotenv`: Environment variable management

Optional system dependency:

- `pdftotext`: Command-line PDF extraction (fallback)

## Changelog

### v1.1.0 (Current)

- **NEW**: Minimal `enumdiff` command for focused enum-gap analysis
- **NEW**: Adaptive provider mode (chat → reasoner escalation)
- **NEW**: SQLite caching for API responses
- **NEW**: Conservative anti-explosion policy
- **IMPROVED**: 80% faster processing vs. full pipeline
- **IMPROVED**: Direct PDF → enum-diff workflow

### v1.0.0 (Legacy)

- Full extraction pipeline with `pack`, `run`, `merge`, `propose` commands
- Comprehensive rule extraction and analysis
- Multi-step workflow for complex use cases

---

## Legacy Commands (Optional)

The original multi-step pipeline is still available for advanced use cases:

```bash
# Legacy workflow (comprehensive rule extraction)
nsgx pack --pdfdir ./data/pdfs --max-chars 4000
nsgx run --concurrency 6
nsgx merge
nsgx propose --min-doc-count 5
```

For most users, the new `enumdiff` command provides the same enum-gap analysis in a single, fast step.

## Contributing

1. Follow the existing code structure and patterns
2. Add tests for new functionality
3. Update this README for new features
4. Ensure all code passes linting and type checking

## License

[Add your license information here]