#!/usr/bin/env python
"""Mimari import sınırı kontrolü (salt-okunur AST analizi).

NEDEN VAR: import-linter, var olmayan modülleri çözemez. Bounded context'lerin
`domain` / `application` / `infrastructure` alt paketleri henüz oluşturulmadığı
için katman bazlı contract'lar (ör. "domain FastAPI import edemez") import-linter
ile HENÜZ ifade edilemez. Bu script aynı kuralları AST üzerinden, dosya yoluna
bakarak zorlar ve boş pakette de çalışır.

Layer paketleri gerçekten oluşturulduğunda bu kuralların import-linter'a
taşınması değerlendirilecektir (bkz. ASM-0011).

Zorlanan kurallar (docs/architecture/dependency-rules.md):
  1. flowpilot.modules.<X>.domain  →  fastapi / sqlalchemy / supabase / psycopg /
                                      alembic / uvicorn  YASAK
  2. flowpilot.modules.<X>.*       →  flowpilot.modules.<Y>.domain           YASAK
                                   →  flowpilot.modules.<Y>.infrastructure   YASAK
  3. flowpilot.api / flowpilot.worker → flowpilot.modules.<X>.domain          YASAK
                                      → flowpilot.modules.<X>.infrastructure  YASAK
                                        (adapter wiring dosyaları hariç)

Bu script PRODUCTION LOGIC İÇERMEZ; yalnız kaynak dosyaları okur ve rapor üretir.
Çıkış kodu: 0 = temiz, 1 = ihlal.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

DOMAIN_FORBIDDEN_ROOTS = frozenset(
    {"fastapi", "uvicorn", "sqlalchemy", "alembic", "psycopg", "supabase", "starlette"}
)

# Adapter wiring composition root'ta tek dosyada toplanır; yalnız o dosyalar
# infrastructure adapter'larını bağlayabilir.
WIRING_FILES = frozenset({"deps.py", "wiring.py"})


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    imported: str
    rule: str

    def render(self, root: Path) -> str:
        rel = self.path.relative_to(root)
        return f"{rel}:{self.line}: {self.rule} -> '{self.imported}'"


def imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    """Dosyadaki tüm import'ları (modül yolu, satır) olarak döndürür."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # göreli import — aynı paket içinde, sınır aşmaz
                continue
            if node.module:
                found.append((node.module, node.lineno))
    return found


def context_of(parts: tuple[str, ...]) -> str | None:
    """`flowpilot.modules.<ctx>...` yolundan context adını çıkarır."""
    if len(parts) >= 3 and parts[0] == "flowpilot" and parts[1] == "modules":
        return parts[2]
    return None


def check_file(path: Path, src_root: Path) -> list[Violation]:
    rel_parts = path.relative_to(src_root).with_suffix("").parts
    module_parts = rel_parts[:-1] if rel_parts[-1] == "__init__" else rel_parts

    own_context = context_of(module_parts)
    in_domain = own_context is not None and "domain" in module_parts
    in_composition_root = len(module_parts) >= 2 and module_parts[1] in {
        "api",
        "worker",
    }
    is_wiring = path.name in WIRING_FILES

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[Violation] = []

    for imported, line in imported_modules(tree):
        root = imported.split(".")[0]
        parts = tuple(imported.split("."))
        target_context = context_of(parts)
        target_layer = parts[3] if len(parts) >= 4 else None

        # Kural 1 — domain katmanında framework / ORM / provider SDK yasak
        if in_domain and root in DOMAIN_FORBIDDEN_ROOTS:
            violations.append(
                Violation(
                    path, line, imported, "domain katmanında framework/ORM/SDK importu"
                )
            )

        # Kural 2 — cross-context domain/infrastructure importu yasak
        if (
            own_context is not None
            and target_context is not None
            and target_context != own_context
            and target_layer in {"domain", "infrastructure"}
        ):
            violations.append(
                Violation(
                    path,
                    line,
                    imported,
                    f"'{own_context}' -> '{target_context}.{target_layer}' cross-context importu",
                )
            )

        # Kural 3 — composition root domain/infrastructure'a doğrudan erişemez
        if (
            in_composition_root
            and not is_wiring
            and target_context is not None
            and target_layer in {"domain", "infrastructure"}
        ):
            violations.append(
                Violation(
                    path,
                    line,
                    imported,
                    f"composition root -> modules.{target_context}.{target_layer} importu",
                )
            )

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "src",
        nargs="?",
        default="apps/backend/src",
        help="Taranacak src kökü (varsayılan: apps/backend/src)",
    )
    args = parser.parse_args(argv)

    src_root = Path(args.src).resolve()
    if not src_root.is_dir():
        print(f"HATA: src kökü bulunamadı: {src_root}", file=sys.stderr)
        return 2

    files = sorted(src_root.rglob("*.py"))
    violations: list[Violation] = []
    for path in files:
        violations.extend(check_file(path, src_root))

    if violations:
        print(f"IMPORT BOUNDARY IHLALI ({len(violations)}):")
        for v in violations:
            print("  " + v.render(src_root))
        return 1

    print(f"import boundaries OK — {len(files)} dosya tarandı, ihlal yok.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
