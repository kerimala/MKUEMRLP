"""Main entry point for nsgx CLI."""

from .cli import cli


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()