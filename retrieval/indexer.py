"""
ECHO Retrieval — Indexer
Scannt Projektdateien, zerlegt sie in Chunks und bereitet sie für die Suche vor.

Design:
- Chunk-Größe: 50 Zeilen mit 10 Zeilen Overlap
- Ignoriert Binary-Files, __pycache__, .git etc.
- Unterstützt: .py, .js, .ts, .html, .css, .md, .txt, .json, .yaml, .yml
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("echo.retrieval.indexer")

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".css", ".md", ".txt",
    ".json", ".yaml", ".yml", ".toml",
    ".env.example", ".sh", ".bat",
}

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".cache", "tmp", "logs",
}

CHUNK_SIZE = 50    # Zeilen pro Chunk
CHUNK_OVERLAP = 10  # Überlappung zwischen Chunks


@dataclass
class Chunk:
    chunk_id: str
    file_path: str          # Relativer Pfad zur Projektroot
    content: str
    start_line: int
    end_line: int
    extension: str

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "file_path": self.file_path,
            "content": self.content,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "extension": self.extension,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Chunk":
        return cls(**d)


def _chunk_id(file_path: str, start_line: int) -> str:
    raw = f"{file_path}:{start_line}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def chunk_file(file_path: Path, project_root: Path) -> list[Chunk]:
    """Liest eine Datei und gibt eine Liste von Chunks zurück."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("Datei nicht lesbar: %s — %s", file_path, exc)
        return []

    lines = text.splitlines()
    if not lines:
        return []

    rel_path = str(file_path.relative_to(project_root))
    ext = file_path.suffix.lower()
    chunks: list[Chunk] = []

    step = CHUNK_SIZE - CHUNK_OVERLAP
    for start in range(0, len(lines), step):
        end = min(start + CHUNK_SIZE, len(lines))
        content = "\n".join(lines[start:end])
        if content.strip():
            chunks.append(Chunk(
                chunk_id=_chunk_id(rel_path, start),
                file_path=rel_path,
                content=content,
                start_line=start + 1,
                end_line=end,
                extension=ext,
            ))
        if end >= len(lines):
            break

    return chunks


def index_project(project_root: Path, max_files: int = 500) -> list[Chunk]:
    """
    Scannt das gesamte Projektverzeichnis und gibt alle Chunks zurück.
    Respektiert IGNORE_DIRS und SUPPORTED_EXTENSIONS.
    """
    all_chunks: list[Chunk] = []
    file_count = 0

    for file_path in sorted(project_root.rglob("*")):
        if file_count >= max_files:
            logger.warning("Max-Dateilimit (%d) erreicht — Scan gestoppt.", max_files)
            break

        # Ignorierte Verzeichnisse überspringen
        if any(part in IGNORE_DIRS for part in file_path.parts):
            continue

        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        chunks = chunk_file(file_path, project_root)
        all_chunks.extend(chunks)
        file_count += 1

    logger.info(
        "Index: %d Dateien gescannt, %d Chunks erstellt.",
        file_count, len(all_chunks),
    )
    return all_chunks
