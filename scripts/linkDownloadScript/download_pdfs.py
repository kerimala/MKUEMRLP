#!/usr/bin/env python3
"""
PDF Downloader Script for Naturschutzgebiete
Downloads PDF files from links extracted from Excel file.
"""

import os
import sys
import re
import requests
import pandas as pd
from pathlib import Path
from urllib.parse import urlparse
from tqdm import tqdm


def extract_pdf_url(html_content):
    """Extract PDF URL from HTML anchor tag."""
    if pd.isna(html_content) or not html_content:
        return None
    
    # Extract URL from <a href="...pdf" ...> pattern
    match = re.search(r'href="([^"]*\.pdf)"', html_content)
    return match.group(1) if match else None


def get_filename_from_url(url):
    """Extract filename from URL."""
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)
    return filename if filename.endswith('.pdf') else f"{filename}.pdf"


def download_file(url, filepath, session):
    """Download a single file with error handling."""
    try:
        response = session.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True, None
    except Exception as e:
        return False, str(e)


def main():
    if len(sys.argv) != 2:
        print("Usage: python download_pdfs.py <excel_file_path>")
        sys.exit(1)
    
    excel_file = sys.argv[1]
    
    if not os.path.exists(excel_file):
        print(f"Error: Excel file '{excel_file}' not found.")
        sys.exit(1)
    
    # Create output directory
    output_dir = Path("Rechtsverordnungen Naturschutzgebiete")
    output_dir.mkdir(exist_ok=True)
    print(f"Output directory: {output_dir.absolute()}")
    
    # Read Excel file
    print(f"Reading Excel file: {excel_file}")
    try:
        df = pd.read_excel(excel_file)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        sys.exit(1)
    
    # Check if 'Rechtsverordnung' column exists
    if 'Rechtsverordnung' not in df.columns:
        print("Error: 'Rechtsverordnung' column not found in Excel file.")
        print(f"Available columns: {list(df.columns)}")
        sys.exit(1)
    
    # Extract PDF URLs
    print("Extracting PDF URLs...")
    pdf_urls = []
    for idx, content in enumerate(df['Rechtsverordnung']):
        url = extract_pdf_url(content)
        if url:
            pdf_urls.append(url)
    
    print(f"Found {len(pdf_urls)} PDF URLs to download")
    
    if not pdf_urls:
        print("No PDF URLs found. Exiting.")
        sys.exit(0)
    
    # Download PDFs
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    downloaded = 0
    skipped = 0
    failed = 0
    
    print("Starting downloads...")
    for url in tqdm(pdf_urls, desc="Downloading PDFs"):
        filename = get_filename_from_url(url)
        filepath = output_dir / filename
        
        if filepath.exists():
            skipped += 1
            continue
        
        success, error = download_file(url, filepath, session)
        if success:
            downloaded += 1
        else:
            failed += 1
            print(f"\nFailed to download {url}: {error}")
    
    # Summary
    print(f"\nDownload complete!")
    print(f"Downloaded: {downloaded}")
    print(f"Skipped (already exists): {skipped}")
    print(f"Failed: {failed}")
    print(f"Total files in directory: {len(list(output_dir.glob('*.pdf')))}")


if __name__ == "__main__":
    main()