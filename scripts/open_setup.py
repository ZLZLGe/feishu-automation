#!/usr/bin/env python3
"""Open a trusted Feishu page used by the guided setup workflow."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from collections.abc import Callable


SETUP_PAGES = {
    "developer-console": "https://open.feishu.cn/app",
    "app-guide": (
        "https://open.feishu.cn/document/quick-access-to-base/"
        "step-1-create-and-configure-an-application?lang=zh-CN"
    ),
    "webhook-guide": (
        "https://open.feishu.cn/document/ukTMukTMukTM/"
        "ucTM5YjL3ETO24yNxkjN?lang=zh-CN"
    ),
}


class SetupOpenError(RuntimeError):
    """Raised when a setup page cannot be selected or opened."""


def open_setup_page(
    page: str,
    *,
    opener: Callable[[str], bool] = webbrowser.open_new_tab,
) -> str:
    try:
        url = SETUP_PAGES[page]
    except KeyError as error:
        choices = ", ".join(sorted(SETUP_PAGES))
        raise SetupOpenError(f"Unknown setup page {page!r}. Choose one of: {choices}") from error

    try:
        opened = opener(url)
    except Exception as error:
        raise SetupOpenError(f"Unable to open the browser: {error}") from error
    if not opened:
        raise SetupOpenError(
            "The default browser did not accept the request. Open this URL manually: "
            f"{url}"
        )
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", choices=sorted(SETUP_PAGES))
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the trusted URL without opening a browser.",
    )
    args = parser.parse_args()
    url = SETUP_PAGES[args.page]
    if args.print_only:
        print(url)
        return 0
    try:
        print(f"Opened: {open_setup_page(args.page)}")
        return 0
    except SetupOpenError as error:
        print(f"open_setup.py: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
