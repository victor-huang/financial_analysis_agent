#!/usr/bin/env python3
"""
Batch financial analysis script that analyzes multiple tickers and generates CSV reports.

Usage:
    python batch_analyze.py AAPL MSFT GOOGL                  # Analyze multiple tickers (next unreported quarter)
    python batch_analyze.py --file tickers.txt               # Read tickers from file
    python batch_analyze.py AAPL --mode latest               # Analyze latest reported quarter (with actuals)
    python batch_analyze.py AAPL --quarter 2025Q2            # Analyze specific quarter

The script will:
1. Create an 'analysis_data_export' directory
2. For each ticker, run financial analysis and save JSON
3. Generate CSV analysis file with all metrics
4. Provide summary of successful and failed analyses
"""

import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime


def create_output_directory(output_dir="analysis_data_export"):
    """Create output directory if it doesn't exist

    Args:
        output_dir: Directory name to create

    Returns:
        Path object for the directory
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    return output_path


def analyze_ticker(ticker, output_dir, verbose=False):
    """Run financial analysis for a ticker

    Args:
        ticker: Stock ticker symbol
        output_dir: Output directory path
        verbose: Whether to show verbose output

    Returns:
        Tuple of (success: bool, json_path: Path or None, error_message: str or None)
    """
    json_filename = f"{ticker.lower()}.json"
    json_path = output_dir / json_filename

    print(f"  📊 Running financial analysis for {ticker}...")

    # Build command
    cmd = [
        sys.executable,
        "-m",
        "financial_analysis_agent.analyze",
        ticker,
        "--analysis-type",
        "financial",
        "--output",
        str(json_path),
    ]

    if verbose:
        cmd.append("--verbose")

    try:
        # Run analysis
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120  # 2 minute timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            return False, None, error_msg

        if not json_path.exists():
            return False, None, f"JSON file not created at {json_path}"

        return True, json_path, None

    except subprocess.TimeoutExpired:
        return False, None, "Analysis timed out after 2 minutes"
    except Exception as e:
        return False, None, str(e)


def generate_csv(json_path, output_dir, quarter=None, mode="next"):
    """Generate CSV analysis from JSON data

    Args:
        json_path: Path to JSON file
        output_dir: Output directory path
        quarter: Optional quarter to analyze (e.g., '2025Q2')
        mode: 'next' for next unreported quarter (default), 'latest' for latest reported quarter

    Returns:
        Tuple of (success: bool, csv_path: Path or None, error_message: str or None)
    """
    ticker = json_path.stem

    if quarter:
        csv_filename = f"{ticker}_{quarter}_analysis.csv"
    else:
        # Will be determined by the script based on current quarter
        # But we need to figure out what it will be called
        csv_filename = f"{ticker}_analysis.csv"  # Placeholder

    csv_path = output_dir / csv_filename

    print(f"  📈 Generating CSV analysis...")

    # Build command
    cmd = [sys.executable, "generate_analysis_csv.py", str(json_path), str(csv_path)]

    if quarter:
        cmd.extend(["--quarter", quarter])

    # Add mode flag
    cmd.extend(["--mode", mode])

    try:
        # Run CSV generation
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            return False, None, error_msg

        # Find the actual CSV file (script may have named it differently)
        csv_files = list(output_dir.glob(f"{ticker}*_analysis.csv"))
        if not csv_files:
            return False, None, f"CSV file not found in {output_dir}"

        # Use the most recently created file
        actual_csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)

        return True, actual_csv_path, None

    except subprocess.TimeoutExpired:
        return False, None, "CSV generation timed out"
    except Exception as e:
        return False, None, str(e)


def process_ticker(ticker, output_dir, quarter=None, mode="next", verbose=False):
    """Process a single ticker: analyze and generate CSV

    Args:
        ticker: Stock ticker symbol
        output_dir: Output directory path
        quarter: Optional quarter to analyze
        mode: 'next' for next unreported quarter (default), 'latest' for latest reported quarter
        verbose: Whether to show verbose output

    Returns:
        Dictionary with results
    """
    result = {
        "ticker": ticker,
        "success": False,
        "json_path": None,
        "csv_path": None,
        "error": None,
        "duration": 0,
    }

    start_time = datetime.now()

    # Step 1: Run financial analysis
    analysis_success, json_path, analysis_error = analyze_ticker(
        ticker, output_dir, verbose
    )

    if not analysis_success:
        result["error"] = f"Analysis failed: {analysis_error}"
        result["duration"] = (datetime.now() - start_time).total_seconds()
        return result

    result["json_path"] = json_path

    # Step 2: Generate CSV
    csv_success, csv_path, csv_error = generate_csv(
        json_path, output_dir, quarter, mode
    )

    if not csv_success:
        result["error"] = f"CSV generation failed: {csv_error}"
        result["duration"] = (datetime.now() - start_time).total_seconds()
        return result

    result["csv_path"] = csv_path
    result["success"] = True
    result["duration"] = (datetime.now() - start_time).total_seconds()

    return result


def read_tickers_from_file(filepath):
    """Read tickers from a text file (one per line)

    Args:
        filepath: Path to file containing tickers

    Returns:
        List of ticker symbols
    """
    tickers = []
    with open(filepath, "r") as f:
        for line in f:
            ticker = line.strip().upper()
            # Skip empty lines and comments
            if ticker and not ticker.startswith("#"):
                tickers.append(ticker)
    return tickers


def print_summary(results):
    """Print summary of batch analysis results

    Args:
        results: List of result dictionaries
    """
    print("\n" + "=" * 90)
    print("BATCH ANALYSIS SUMMARY")
    print("=" * 90)

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"\n✅ Successful: {len(successful)}/{len(results)}")
    print(f"❌ Failed: {len(failed)}/{len(results)}")
    print(f"⏱️  Total time: {sum(r['duration'] for r in results):.1f}s")

    if successful:
        print("\n" + "-" * 90)
        print("SUCCESSFUL ANALYSES:")
        print("-" * 90)
        for r in successful:
            print(
                f"  ✓ {r['ticker']:<6} - JSON: {r['json_path'].name}, CSV: {r['csv_path'].name} ({r['duration']:.1f}s)"
            )

    if failed:
        print("\n" + "-" * 90)
        print("FAILED ANALYSES:")
        print("-" * 90)
        for r in failed:
            print(f"  ✗ {r['ticker']:<6} - {r['error']}")

    print("\n" + "=" * 90)


def main():
    parser = argparse.ArgumentParser(
        description="Batch financial analysis for multiple tickers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze multiple tickers (next unreported quarter - default)
  python batch_analyze.py AAPL MSFT GOOGL

  # Analyze latest reported quarter (with actuals)
  python batch_analyze.py AAPL MSFT --mode latest

  # Read tickers from file
  python batch_analyze.py --file tickers.txt

  # Analyze specific quarter
  python batch_analyze.py AAPL MSFT --quarter 2025Q2

  # With verbose output
  python batch_analyze.py AAPL --verbose

  # Custom output directory
  python batch_analyze.py AAPL --output-dir my_analysis
        """,
    )

    parser.add_argument("tickers", nargs="*", help="Stock ticker symbols to analyze")
    parser.add_argument("--file", "-f", help="Read tickers from file (one per line)")
    parser.add_argument(
        "--quarter",
        "-q",
        help="Quarter to analyze (e.g., 2025Q2). Overrides --mode if specified.",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["next", "latest"],
        default="next",
        help="Quarter selection mode: 'next' for next unreported quarter (default), 'latest' for latest reported quarter with actuals",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="analysis_data_export",
        help="Output directory (default: analysis_data_export)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show verbose output from analysis"
    )

    args = parser.parse_args()

    # Get tickers from arguments or file
    tickers = []
    if args.file:
        try:
            tickers = read_tickers_from_file(args.file)
            print(f"📁 Read {len(tickers)} tickers from {args.file}")
        except Exception as e:
            print(f"Error reading file {args.file}: {e}")
            return 1
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        print("Error: No tickers specified. Use positional arguments or --file.")
        parser.print_help()
        return 1

    if not tickers:
        print("Error: No tickers to process")
        return 1

    # Create output directory
    output_dir = create_output_directory(args.output_dir)
    print(f"📂 Output directory: {output_dir.absolute()}")
    print(f"🎯 Processing {len(tickers)} ticker(s)...")
    print()

    # Process each ticker
    results = []
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Processing {ticker}...")
        result = process_ticker(
            ticker, output_dir, args.quarter, args.mode, args.verbose
        )
        results.append(result)

        if result["success"]:
            print(f"  ✅ Success! ({result['duration']:.1f}s)")
        else:
            print(f"  ❌ Failed: {result['error']}")
        print()

    # Print summary
    print_summary(results)

    # Return exit code based on results
    failed_count = sum(1 for r in results if not r["success"])
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
