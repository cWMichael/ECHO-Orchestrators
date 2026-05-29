"""
ECHO Retrieval — Searcher
Keyword-basierte Suche über den Index.

Phase 1: TF-gewichtete Keyword-Suche — kein Embedding-Modell nötig.
Phase 2 (später): Semantische Suche via Ollama-Embeddings.

Scoring:
- Exakte Phrase: +3 Punkte
- Jedes Keyword einzeln: +1 Punkt
- Treffer im Dateinamen: +2 Bonus
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from retrieval.indexer import Chunk
from retrieval.store import get_or_build_index

logger = logging.getLogger("echo.retrieval.searcher")


@dataclass
class SearchResult:
    chunk: Chunk
    score: float
    highlights: list[str]

    def to_dict(self) -> dict:
        return {
            "file_path": self.chunk.file_path,
            "start_line": self.chunk.start_line,
            "end_line": self.chunk.end_line,
            "score": round(self.score, 3),
            "highlights": self.highlights,
            "content_preview": self.chunk.content[:300],
        }


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"\w+", text) if len(t) > 2]


def _score_chunk(chunk: Chunk, keywords: list[str], phrase: str) -> tuple[float, list[str]]:
    content_lower = chunk.content.lower()
    file_lower = chunk.file_path.lower()
    score = 0.0
    highlights: list[str] = []

    # Exakte Phrase
    if phrase and phrase.lower() in content_lower:
        score += 3.0
        highlights.append(f'Phrase gefunden: "{phrase}"')

    # Einzelne Keywords
    for kw in keywords:
        if kw in content_lower:
            score += 1.0
            # Highlight-Zeile finden
            for line in chunk.content.splitlines():
                if kw in line.lower():
                    highlights.append(line.strip()[:100])
                    break

    # Bonus wenn Keyword im Dateinamen
    for kw in keywords:
        if kw in file_lower:
            score += 2.0
            highlights.append(f"[Datei: {chunk.file_path}]")

    return score, highlights[:5]


def search(
    query: str,
    project_root: Path,
    top_k: int = 5,
    min_score: float = 1.0,
) -> list[SearchResult]:
    """
    Durchsucht den Index nach der Query.
    Gibt die top_k relevantesten Chunks zurück.
    """
    index = get_or_build_index(project_root)
    chunks = [Chunk.from_dict(c) for c in index.get("chunks", [])]

    if not chunks:
        logger.warning("Leerer Index — keine Suchergebnisse.")
        return []

    keywords = _tokenize(query)
    phrase = query.strip()

    scored: list[SearchResult] = []
    for chunk in chunks:
        score, highlights = _score_chunk(chunk, keywords, phrase)
        if score >= min_score:
            scored.append(SearchResult(chunk=chunk, score=score, highlights=highlights))

    scored.sort(key=lambda r: r.score, reverse=True)
    results = scored[:top_k]

    logger.info(
        "Suche: '%s' | %d Treffer (von %d Chunks)",
        query, len(results), len(chunks),
    )
    return results


def format_results_for_prompt(results: list[SearchResult], max_chars: int = 3000) -> str:
    """Formatiert Suchergebnisse als kompakten Kontext-String für Worker-Prompts."""
    if not results:
        return "Keine relevanten Dokumente gefunden."

    parts = ["## RELEVANTE DOKUMENTE AUS DEM WISSENSSPEICHER\n"]
    total_chars = 0

    for i, result in enumerate(results, 1):
        block = (
            f"### [{i}] {result.chunk.file_path} "
            f"(Zeilen {result.chunk.start_line}–{result.chunk.end_line}, "
            f"Score: {result.score:.1f})\n"
            f"{result.chunk.content[:500]}\n"
        )
        if total_chars + len(block) > max_chars:
            break
        parts.append(block)
        total_chars += len(block)

    return "\n".join(parts)
