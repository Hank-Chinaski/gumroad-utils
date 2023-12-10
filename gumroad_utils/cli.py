from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser

from pathlib3x import Path

__all__ = ["get_cli_arg_parser"]


def _is_valid_path(file_path: str) -> Path:
    path = Path(file_path)
    if path.exists():
        return path
    else:
        raise FileNotFoundError(file_path)


def _to_path(file_path: str) -> Path:
    return Path(file_path)


def get_cli_arg_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description="A simple downloader for gumroad.com products",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "link",
        nargs="*",
        default="library",
        help="A product link or a list of them.",
    )
    parser.add_argument(
        "--debug",
        help="Enable debug mode.",
        action="store_true",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=_is_valid_path,
        help="A path to configuration INI file.",
        default="config.ini",
    )
    parser.add_argument(
        "-l",
        "--links",
        type=_is_valid_path,
        help="A file with a list of products links.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=_to_path,
        help="An output directory (default: current directory).",
        default=Path.cwd(),
    )

    return parser
