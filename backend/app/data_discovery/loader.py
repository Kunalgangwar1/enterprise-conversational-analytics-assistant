"""Load small dataset registrations and enrich them from MetadataRegistry."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.data_discovery.exceptions import DataDiscoveryConfigurationError
from app.data_discovery.models import DatasetRegistration, DatasetRegistryConfig
from app.metadata.exceptions import MetadataNotFoundError
from app.metadata.registry import MetadataRegistry

DEFAULT_DATASET_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "data_discovery" / "datasets.yaml"
)


def load_dataset_registry(
    metadata: MetadataRegistry,
    path: Path = DEFAULT_DATASET_REGISTRY_PATH,
) -> tuple[DatasetRegistration, ...]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        config = DatasetRegistryConfig.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise DataDiscoveryConfigurationError("Invalid Data Discovery registry") from exc

    registrations: list[DatasetRegistration] = []
    try:
        for item in config.datasets:
            repository = item.get("repository", "")
            if not repository.startswith("datasets-"):
                raise DataDiscoveryConfigurationError(
                    "Every Data Discovery repository must start with datasets-"
                )
            table = metadata.get_table(item.get("table", ""))
            domain = metadata.get_domain(item.get("domain", ""))
            if table.name not in domain.tables or domain.name not in table.domains:
                raise DataDiscoveryConfigurationError(
                    f"Discovery registration is inconsistent for table {table.name}"
                )
            registrations.append(
                DatasetRegistration(
                    dataset=item.get("dataset", ""),
                    repository=repository,
                    table=table.name,
                    domain=domain.name,
                    description=table.description,
                    table_aliases=tuple(table.aliases),
                    columns={column.name: tuple(column.aliases) for column in table.columns},
                )
            )
    except (MetadataNotFoundError, ValidationError) as exc:
        raise DataDiscoveryConfigurationError(
            "Data Discovery registry references unknown metadata"
        ) from exc
    return tuple(sorted(registrations, key=lambda item: item.dataset))
