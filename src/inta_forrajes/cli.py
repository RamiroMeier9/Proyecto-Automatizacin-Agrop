from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .pipeline import Pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inta-forrajes",
        description="Actualización y evaluación económica de alternativas forrajeras",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="Inicializa la base SQLite")
    subparsers.add_parser("import-manual", help="Importa las plantillas CSV completadas")

    update = subparsers.add_parser("update", help="Actualiza fuentes automáticas")
    update.add_argument("--source", choices=["all", "bcra", "sio", "a3"], default="all")

    subparsers.add_parser("discover-a3", help="Descarga el catálogo de instrumentos de A3")

    evaluate = subparsers.add_parser("evaluate", help="Evalúa una alternativa")
    evaluate.add_argument("--alternative", required=True)
    evaluate.add_argument("--rate", type=float, default=None, help="Tasa anual en formato decimal")
    evaluate.add_argument("--yield-dm", type=float, default=None, help="Rendimiento anual kg MS/ha")

    subparsers.add_parser("snapshot", help="Genera el último snapshot JSON")
    subparsers.add_parser(
        "publish-public",
        help="Genera un snapshot reproducible únicamente con fuentes públicas",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pipeline = Pipeline()
    if args.command == "init-db":
        print(json.dumps({"status": "ok", "database": str(pipeline.paths.db)}, ensure_ascii=False))
    elif args.command == "import-manual":
        print(json.dumps(pipeline.import_manual(), ensure_ascii=False, indent=2))
    elif args.command == "update":
        print(json.dumps(pipeline.update(args.source), ensure_ascii=False, indent=2))
    elif args.command == "discover-a3":
        print(json.dumps({"output": str(pipeline.discover_a3())}, ensure_ascii=False))
    elif args.command == "evaluate":
        print(
            json.dumps(
                asdict(pipeline.evaluate(args.alternative, args.rate, args.yield_dm)),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "snapshot":
        print(json.dumps({"output": str(pipeline.write_snapshot())}, ensure_ascii=False))
    elif args.command == "publish-public":
        print(json.dumps({"output": str(pipeline.write_public_snapshot())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
