"""CLI interface for NSG extraction tool."""

import click
import os
from pathlib import Path

from dotenv import load_dotenv

from .utils import setup_logging


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """NSG Regulation Extraction Tool."""
    # Load environment variables from .env file
    load_dotenv()
    
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    
    # Setup logging
    logger = setup_logging()
    if verbose:
        logger.setLevel('DEBUG')
    
    ctx.obj['logger'] = logger


@cli.command()
@click.option('--pdfdir', required=True, help='Directory containing PDF files (recursive)')
@click.option('--max-chars', default=4000, help='Maximum characters per chunk (default: 4000)')
@click.option('--output-dir', default='out', help='Output directory (default: out)')
@click.pass_context
def pack(ctx: click.Context, pdfdir: str, max_chars: int, output_dir: str) -> None:
    """Convert PDFs to text chunks (JSONL format)."""
    from .pack import pack_pdfs_to_chunks
    
    logger = ctx.obj['logger']
    logger.info(f"Starting pack command: pdfdir={pdfdir}, max_chars={max_chars}")
    
    try:
        pack_pdfs_to_chunks(pdfdir, max_chars, output_dir, logger)
        logger.info("Pack command completed successfully")
    except Exception as e:
        logger.error(f"Pack command failed: {e}")
        raise click.ClickException(f"Failed to pack PDFs: {e}")


@cli.command()
@click.option('--chunks-file', default='out/chunks.jsonl', help='Input chunks file')
@click.option('--output-dir', default='out', help='Output directory')
@click.option('--concurrency', default=4, help='Number of concurrent requests (default: 4)')
@click.option('--force', is_flag=True, help='Overwrite existing results')
@click.pass_context
def run(ctx: click.Context, chunks_file: str, output_dir: str, concurrency: int, force: bool) -> None:
    """Process chunks with DeepSeek API."""
    from .run import process_chunks_with_deepseek
    
    logger = ctx.obj['logger']
    logger.info(f"Starting run command: chunks_file={chunks_file}, concurrency={concurrency}")
    
    # Check environment variables
    required_env_vars = ['DEEPSEEK_ENDPOINT', 'DEEPSEEK_MODEL', 'DEEPSEEK_API_KEY']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        raise click.ClickException(
            f"Missing environment variables: {', '.join(missing_vars)}\n"
            "Please set DEEPSEEK_ENDPOINT, DEEPSEEK_MODEL, and DEEPSEEK_API_KEY in .env file or as environment variables"
        )
    
    try:
        process_chunks_with_deepseek(chunks_file, output_dir, concurrency, force, logger)
        logger.info("Run command completed successfully")
    except Exception as e:
        logger.error(f"Run command failed: {e}")
        raise click.ClickException(f"Failed to process chunks: {e}")


@cli.command()
@click.option('--input-dir', default='out/chunk_results', help='Directory with chunk results')
@click.option('--output-dir', default='out/docs', help='Output directory for merged documents')
@click.option('--force', is_flag=True, help='Overwrite existing results')
@click.pass_context
def merge(ctx: click.Context, input_dir: str, output_dir: str, force: bool) -> None:
    """Merge chunk results into document-level results."""
    from .merge import merge_chunk_results
    
    logger = ctx.obj['logger']
    logger.info(f"Starting merge command: input_dir={input_dir}, output_dir={output_dir}")
    
    try:
        merge_chunk_results(input_dir, output_dir, force, logger)
        logger.info("Merge command completed successfully")
    except Exception as e:
        logger.error(f"Merge command failed: {e}")
        raise click.ClickException(f"Failed to merge results: {e}")


@cli.command()
@click.option('--docs-dir', default='out/docs', help='Directory with document results')
@click.option('--output-dir', default='.', help='Output directory for proposals')
@click.option('--min-doc-count', default=5, help='Minimum document count for new candidates (default: 5)')
@click.option('--force', is_flag=True, help='Overwrite existing results')
@click.pass_context
def propose(ctx: click.Context, docs_dir: str, output_dir: str, min_doc_count: int, force: bool) -> None:
    """Generate candidate proposals and DBML patches."""
    from .propose import generate_proposals
    
    logger = ctx.obj['logger']
    logger.info(f"Starting propose command: docs_dir={docs_dir}, min_doc_count={min_doc_count}")
    
    try:
        generate_proposals(docs_dir, output_dir, min_doc_count, force, logger)
        logger.info("Propose command completed successfully")
    except Exception as e:
        logger.error(f"Propose command failed: {e}")
        raise click.ClickException(f"Failed to generate proposals: {e}")


@cli.command()
@click.option('--pdfdir', required=True, help='Directory containing PDF files (recursive)')
@click.option('--out', default='./out/enumdiff', help='Output directory (default: ./out/enumdiff)')
@click.option('--provider-mode', 
              type=click.Choice(['chat', 'reasoner', 'auto']), 
              default='auto',
              help='LLM provider mode: chat (fast), reasoner (thorough), auto (adaptive)')
@click.option('--concurrency', default=4, help='Number of concurrent API requests (default: 4)')
@click.option('--min-doc-count', default=5, help='Minimum document count for new candidates (default: 5)')
@click.option('--force', is_flag=True, help='Overwrite existing outputs')
@click.pass_context
def enumdiff(ctx: click.Context, pdfdir: str, out: str, provider_mode: str, 
             concurrency: int, min_doc_count: int, force: bool) -> None:
    """Extract enum-diff proposals from NSG PDFs (minimal, fast workflow)."""
    from .enumdiff import run_enumdiff
    
    logger = ctx.obj['logger']
    logger.info(f"Starting enumdiff command: pdfdir={pdfdir}, provider_mode={provider_mode}")
    
    # Check environment variables
    required_env_vars = ['DEEPSEEK_ENDPOINT', 'DEEPSEEK_API_KEY']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        raise click.ClickException(
            f"Missing environment variables: {', '.join(missing_vars)}\n"
            "Please set DEEPSEEK_ENDPOINT and DEEPSEEK_API_KEY in .env file or as environment variables\n"
            "Optional: DEEPSEEK_MODEL_CHAT (default: deepseek-chat), DEEPSEEK_MODEL_REASONER (default: deepseek-reasoner)"
        )
    
    try:
        run_enumdiff(pdfdir, out, provider_mode, concurrency, min_doc_count, force, logger)
        logger.info("Enumdiff command completed successfully")
    except Exception as e:
        logger.error(f"Enumdiff command failed: {e}")
        raise click.ClickException(f"Failed to run enum-diff: {e}")


if __name__ == '__main__':
    cli()