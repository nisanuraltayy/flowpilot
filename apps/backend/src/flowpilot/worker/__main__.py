"""Worker composition root — entrypoint.

Bu aşamada YALNIZCA `--check` desteklenir:

    python -m flowpilot.worker --check

`--check` gerçek worker döngüsünü BAŞLATMAZ. Outbox, timer veya queue
İŞLEMEZ. Yalnızca paket importunun ve ayar yüklemesinin başarılı olduğunu
doğrular ve exit code 0 döner.

Gerçek worker loop, SIGTERM yönetimi, outbox polling ve bounded retry
ilgili story'lerde (E09) eklenecektir.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from flowpilot.config.settings import Settings, get_settings

CHECK_OK_MESSAGE = "flowpilot.worker check ok"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m flowpilot.worker",
        description="FlowPilot worker composition root (scaffold — henüz worker loop yok).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        required=True,
        help="Paket importunu ve ayar yüklemesini doğrula, sonra çık. Worker loop BAŞLATMAZ.",
    )
    return parser


def run_check(settings: Settings) -> str:
    """Doğrulama mesajını üretir. Yan etkisi yoktur."""
    return f"{CHECK_OK_MESSAGE} (env={settings.app_environment}, log_level={settings.log_level})"


def main(argv: Sequence[str] | None = None) -> int:
    """Entrypoint. Başarılıysa 0 döner; argparse hatalı argümanda 2 ile çıkar."""
    parser = _build_parser()
    parser.parse_args(argv)

    settings = get_settings()
    print(run_check(settings))  # CLI ciktisi: worker check sonucu
    return 0


if __name__ == "__main__":
    sys.exit(main())
