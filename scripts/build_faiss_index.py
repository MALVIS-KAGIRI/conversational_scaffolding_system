from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data" / "knowledge_base.jsonl"
OUTPUT_DIR = ROOT / "data" / "faiss"
INDEX_PATH = OUTPUT_DIR / "coaching.index"
METADATA_PATH = OUTPUT_DIR / "coaching_metadata.json"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def load_documents() -> list[dict]:
    documents = []
    with KB_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            documents.append(json.loads(line))
    return documents


def build_index(
    kb_path: Path = KB_PATH,
    output_dir: Path = OUTPUT_DIR,
    index_path: Path = INDEX_PATH,
    metadata_path: Path = METADATA_PATH,
    embedding_model_name: str = EMBEDDING_MODEL_NAME,
) -> None:
    try:
        import faiss  # type: ignore
        import numpy as np  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing dependencies. Install faiss-cpu, sentence-transformers, and numpy."
        ) from exc

    documents = load_documents() if kb_path == KB_PATH else _load_documents_from_path(kb_path)
    texts = [
        " ".join(
            [
                doc["scenario"],
                doc["intent"],
                doc["skill"],
                doc["type"],
                doc["content"],
                " ".join(doc.get("tags", [])),
            ]
        )
        for doc in documents
    ]

    model = SentenceTransformer(embedding_model_name)
    embeddings = model.encode(texts, normalize_embeddings=True)
    matrix = np.asarray(embeddings, dtype="float32")

    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)

    output_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(documents, handle, indent=2)

    print(f"Built FAISS index with {len(documents)} documents.")
    print(f"Index: {index_path}")
    print(f"Metadata: {metadata_path}")


def _load_documents_from_path(path: Path) -> list[dict]:
    documents = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            documents.append(json.loads(line))
    return documents


def main() -> None:
    build_index()


if __name__ == "__main__":
    main()
