from __future__ import annotations

import argparse
import json
import sys

from .errors import EasyReelsError
from .pipeline import ReelsPipeline
from .project import initialize_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="easy-reels",
        description="Easy Reels Generator by ProAI — ядро этапа 1",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-project", help="создать папки и шаблоны")
    init.add_argument("project", help="путь к папке проекта")

    check = subparsers.add_parser("check", help="проверить входные файлы")
    check.add_argument("project", help="путь к папке проекта")
    check.add_argument("--ffmpeg", default="ffmpeg")
    check.add_argument("--ffprobe", default="ffprobe")

    render = subparsers.add_parser("render-one", help="создать один ролик")
    render.add_argument("project", help="путь к папке проекта")
    render.add_argument("--seed", type=int, default=None)
    render.add_argument("--ffmpeg", default="ffmpeg")
    render.add_argument("--ffprobe", default="ffprobe")
    render.add_argument("--encoder", default=None)

    batch = subparsers.add_parser("render-all", help="создать все ролики по очереди")
    batch.add_argument("project", help="путь к папке проекта")
    batch.add_argument("--seed", type=int, default=None)
    batch.add_argument("--ffmpeg", default="ffmpeg")
    batch.add_argument("--ffprobe", default="ffprobe")
    batch.add_argument("--encoder", default=None)

    preview = subparsers.add_parser(
        "preview", help="создать новый тестовый ролик в папке preview"
    )
    preview.add_argument("project", help="путь к папке проекта")
    preview.add_argument("--seed", type=int, default=None)
    preview.add_argument("--ffmpeg", default="ffmpeg")
    preview.add_argument("--ffprobe", default="ffprobe")
    preview.add_argument("--encoder", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init-project":
            paths = initialize_project(args.project)
            print(f"Проект создан: {paths.root}")
            return 0
        pipeline = ReelsPipeline(
            args.project,
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
            encoder=getattr(args, "encoder", None),
        )
        if args.command == "check":
            report = pipeline.check()
            print(json.dumps(asdict_compatible(report), ensure_ascii=False, indent=2))
            return 0
        if args.command == "render-one":
            result = pipeline.render_one(seed=args.seed)
            print(f"Готово: {result.output_path}")
            return 0
        if args.command == "render-all":
            result = pipeline.run_batch(
                seed=args.seed,
                progress=lambda update: print(update.message),
            )
            return 0 if not result.row_errors else 3
        if args.command == "preview":
            result = pipeline.render_preview(seed=args.seed)
            print(f"Предпросмотр готов: {result.output_path}")
            return 0
    except EasyReelsError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 2


def asdict_compatible(value) -> dict:
    return {
        "pending_row": value.pending_row,
        "pending_rows": value.pending_rows,
        "valid_videos": value.valid_videos,
        "valid_music": value.valid_music,
        "silent_mode": value.silent_mode,
        "warnings": list(value.warnings),
    }


if __name__ == "__main__":
    raise SystemExit(main())
