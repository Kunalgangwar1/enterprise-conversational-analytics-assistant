"""Safe deterministic loader for synthetic Data Quality guidance."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.data_quality.exceptions import DataQualityLoadError
from app.data_quality.models import DataQualityDocument


class DataQualityLoader:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def load(self) -> tuple[DataQualityDocument, ...]:
        if not self._root.is_dir():
            raise DataQualityLoadError(f"Data Quality directory not found: {self._root}")
        documents: list[DataQualityDocument] = []
        ids: set[str] = set()
        for source in sorted(self._root.rglob("*.md")):
            resolved = source.resolve()
            if not resolved.is_relative_to(self._root):
                raise DataQualityLoadError(f"Data Quality source escapes configured root: {source}")
            metadata, text = _front_matter(resolved)
            try:
                document = DataQualityDocument.model_validate(
                    {
                        **metadata,
                        "source_path": resolved.relative_to(self._root).as_posix(),
                        "text": text,
                    }
                )
            except ValidationError as exc:
                raise DataQualityLoadError(f"Invalid Data Quality document: {source}") from exc
            if document.id in ids:
                raise DataQualityLoadError(f"Duplicate Data Quality document ID: {document.id}")
            ids.add(document.id)
            documents.append(document)
        if not documents:
            raise DataQualityLoadError("Data Quality corpus contains no documents")
        return tuple(documents)


def _front_matter(path: Path) -> tuple[dict[str, object], str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise DataQualityLoadError(f"Data Quality document lacks front matter: {path}")
    try:
        closing = lines.index("---", 1)
        metadata = yaml.safe_load("\n".join(lines[1:closing]))
    except (ValueError, yaml.YAMLError) as exc:
        raise DataQualityLoadError(f"Malformed Data Quality front matter: {path}") from exc
    text = "\n".join(lines[closing + 1 :]).strip()
    if not isinstance(metadata, dict) or not text:
        raise DataQualityLoadError(f"Incomplete Data Quality document: {path}")
    return metadata, text
