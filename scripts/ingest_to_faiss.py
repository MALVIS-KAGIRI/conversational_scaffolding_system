from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterable, List

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_faiss_index import KB_PATH, build_index


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".jsonl", ".csv"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract text from downloaded files and store it in the FAISS knowledge base."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more files or directories containing downloaded source documents.",
    )
    parser.add_argument("--source", default="user_import", help="Source label stored in the knowledge base.")
    parser.add_argument("--scenario", default="small_talk_flow", help="Scenario metadata for imported chunks.")
    parser.add_argument("--intent", default="general_interaction", help="Intent metadata for imported chunks.")
    parser.add_argument("--skill", default="conversation_flow", help="Skill metadata for imported chunks.")
    parser.add_argument("--type", dest="doc_type", default="coaching_snippet", help="Document type metadata.")
    parser.add_argument("--tags", default="", help="Comma-separated tags to attach to each chunk.")
    parser.add_argument("--replace-source", action="store_true", help="Remove older chunks from the same source before appending new ones.")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild the FAISS index after ingestion.")
    parser.add_argument("--chunk-size", type=int, default=450, help="Approximate chunk size in characters.")
    parser.add_argument("--chunk-overlap", type=int, default=80, help="Approximate overlap between chunks.")
    return parser.parse_args()


def collect_files(raw_inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw_input in raw_inputs:
        path = Path(raw_input).expanduser().resolve()
        if path.is_dir():
            for candidate in path.rglob("*"):
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append(candidate)
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return sorted(set(files))


def extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".json":
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        return flatten_json_text(payload)
    if suffix == ".jsonl":
        texts = []
        for line in file_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                texts.append(flatten_json_text(json.loads(line)))
        return "\n".join(texts)
    if suffix == ".csv":
        rows = []
        with file_path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(" ".join(str(value) for value in row.values() if value))
        return "\n".join(rows)
    return ""


def flatten_json_text(payload: object) -> str:
    if isinstance(payload, dict):
        preferred_keys = ["content", "text", "body", "message", "response", "dialogue", "utterance"]
        fragments: List[str] = []
        for key in preferred_keys:
            if key in payload:
                fragments.append(flatten_json_text(payload[key]))
        if fragments:
            return "\n".join(fragment for fragment in fragments if fragment)
        return "\n".join(flatten_json_text(value) for value in payload.values())
    if isinstance(payload, list):
        return "\n".join(flatten_json_text(item) for item in payload)
    return str(payload)


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks = []
    start = 0
    step = max(1, chunk_size - chunk_overlap)
    while start < len(cleaned):
        chunk = cleaned[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def load_existing_documents(path: Path) -> list[dict]:
    if not path.exists():
        return []
    documents = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                documents.append(json.loads(line))
    return documents


def write_documents(path: Path, documents: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document, ensure_ascii=True) + "\n")


def ingest_documents(args: argparse.Namespace) -> int:
    files = collect_files(args.inputs)
    if not files:
        print("No supported files found to ingest.")
        return 0

    existing_documents = load_existing_documents(KB_PATH)
    if args.replace_source:
        existing_documents = [doc for doc in existing_documents if doc.get("source") != args.source]

    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    new_documents = []
    for file_path in files:
        extracted = extract_text(file_path)
        for index, chunk in enumerate(chunk_text(extracted, args.chunk_size, args.chunk_overlap), start=1):
            new_documents.append(
                {
                    "id": f"{args.source}_{file_path.stem}_{index}",
                    "type": args.doc_type,
                    "scenario": args.scenario,
                    "intent": args.intent,
                    "skill": args.skill,
                    "content": chunk,
                    "source": args.source,
                    "tags": tags + [file_path.suffix.lower().lstrip(".")],
                }
            )

    merged = existing_documents + new_documents
    KB_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_documents(KB_PATH, merged)
    print(f"Imported {len(new_documents)} chunks from {len(files)} file(s) into {KB_PATH}.")

    if args.rebuild:
        build_index()

    return len(new_documents)


def main() -> None:
    args = parse_args()
    ingest_documents(args)


if __name__ == "__main__":
    main()
