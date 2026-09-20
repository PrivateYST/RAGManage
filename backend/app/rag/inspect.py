"""Read-only local corpus inspection; no publication or model calls by default."""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from io import TextIOWrapper
from pathlib import Path

from app.core.config import Settings
from app.rag.models import ModelGatewayClient
from app.rag.parsing import parse_document


async def inspect(directory: Path, query: str | None) -> None:
    if not directory.is_dir():
        raise ValueError("CORPUS_DIRECTORY_NOT_FOUND")
    documents = [parse_document(path) for path in sorted(directory.iterdir()) if path.is_file()]
    if query is None:
        print(json.dumps([asdict(doc) for doc in documents], ensure_ascii=False, indent=2))
        return
    # This diagnostic searches complete sources only, before formal chunking and publication.
    candidates = [
        (doc, block) for doc in documents if doc.status == "complete" for block in doc.blocks
    ]
    if not candidates:
        raise ValueError("NO_COMPLETE_SOURCES")
    client = ModelGatewayClient(Settings())
    vectors = []
    for offset in range(0, len(candidates), 16):
        vectors.extend(
            await client.embed([block.text for _, block in candidates[offset : offset + 16]])
        )
    query_vector = (
        await client.embed(
            [
                f"Instruct: Retrieve relevant passages that answer the query\nQuery: {query}",
            ]
        )
    )[0]
    ranked = sorted(
        zip(candidates, vectors, strict=True),
        key=lambda pair: sum(x * y for x, y in zip(query_vector, pair[1], strict=True)),
        reverse=True,
    )
    print(
        json.dumps(
            [
                {"document": doc.name, "sha256": doc.sha256, **asdict(block)}
                for (doc, block), _ in ranked[:10]
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--query", help="Explicitly send corpus text to the configured model gateway for recall"
    )
    args = parser.parse_args()
    asyncio.run(inspect(args.directory, args.query))
