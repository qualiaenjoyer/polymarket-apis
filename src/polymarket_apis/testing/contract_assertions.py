from __future__ import annotations

import inspect
import json
import keyword
import os
import re
from dataclasses import dataclass
from pathlib import Path
from types import NoneType, UnionType
from typing import Annotated, Any, NoReturn, Union, get_args, get_origin

import httpx
import pytest
from pydantic import BaseModel, RootModel, TypeAdapter, ValidationError
from pydantic.aliases import AliasChoices, AliasPath

SNAPSHOT_DIR = Path(__file__).resolve().parents[3] / "tests" / "prod_read" / "snapshots"
AUTO_EXPAND_CONTRACT = os.getenv("AUTO_EXPAND_CONTRACT") == "1"
UPDATE_SNAPSHOTS = os.getenv("UPDATE_SCHEMA_SNAPSHOTS") == "1" or AUTO_EXPAND_CONTRACT
EXPANSION_REPORT_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "prod_read"
    / "contract_expansion_report.json"
)

_REPORT_ROWS: list[dict[str, str]] = []
_PATCHED_FIELDS: set[tuple[str, str, str]] = set()


@dataclass(frozen=True)
class UnknownFieldObservation:
    owner_model: type[BaseModel]
    path: str
    alias: str
    sample_value: Any


def fetch_json(
    name: str,
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        fail_contract(
            "endpoint unavailable",
            (
                f"{name} returned HTTP {exc.response.status_code}.\n"
                f"URL: {exc.request.url}\n"
                "This looks like endpoint instability, auth/rate limiting, or an upstream outage."
            ),
        )
    except httpx.RequestError as exc:
        fail_contract(
            "endpoint unavailable",
            (
                f"{name} request failed before a valid response was received.\n"
                f"URL: {exc.request.url}\n"
                f"Error: {exc!r}"
            ),
        )
    else:
        return response.json()


def assert_api_contract(name: str, annotation: Any, payload: Any) -> Any:
    try:
        validated = TypeAdapter(annotation).validate_python(payload)
    except ValidationError as exc:
        fail_contract("schema mismatch", _validation_message(name, payload, exc))

    observed_shape = sorted(_collect_shape(payload))
    snapshot_path = SNAPSHOT_DIR / f"{_snapshot_slug(name)}.json"
    known_shape = _read_known_shape(snapshot_path)
    added_paths = sorted(set(observed_shape) - set(known_shape))

    unknown_observations = _collect_unknown_field_observations(annotation, payload)

    if AUTO_EXPAND_CONTRACT:
        _merge_shape_snapshot(snapshot_path, name, observed_shape)
        if unknown_observations:
            _apply_model_patches(name, unknown_observations)
        return validated

    if UPDATE_SNAPSHOTS:
        _merge_shape_snapshot(snapshot_path, name, observed_shape)
        return validated

    if added_paths or unknown_observations:
        fail_contract(
            "contract expanded",
            _contract_expanded_message(
                name,
                snapshot_path,
                added_paths,
                unknown_observations,
            ),
        )

    return validated


def fail_contract(category: str, message: str) -> NoReturn:
    pytest.fail(f"[{category}] {message}")


def _validation_message(name: str, payload: Any, exc: ValidationError) -> str:
    first_error = exc.errors()[0]
    return (
        f"{name} schema drift detected.\n"
        f"Validation path: {first_error['loc']}\n"
        f"Validation message: {first_error['msg']}\n"
        f"Payload type: {type(payload).__name__}\n"
        "Run this test locally to inspect the full response body."
    )


def _contract_expanded_message(
    name: str,
    snapshot_path: Path,
    added_paths: list[str],
    unknown_observations: list[UnknownFieldObservation],
) -> str:
    message = (
        f"{name} expanded beyond the currently modeled contract.\n"
        f"Snapshot: {snapshot_path}\n"
    )
    if added_paths:
        message += f"New paths/types:\n{_format_items(added_paths)}\n"
    if unknown_observations:
        message += "New unmapped model fields:\n"
        message += _format_items(
            [
                f"{obs.path} -> {obs.owner_model.__module__}.{obs.owner_model.__name__}"
                for obs in unknown_observations
            ]
        )
        message += "\n"
    message += (
        "Run the auto-expansion workflow to update snapshots and generate a PR "
        "for new model fields."
    )
    return message


def _collect_shape(payload: Any, path: str = "$") -> set[str]:
    shape = {f"{path}:{_json_type_name(payload)}"}

    if isinstance(payload, dict):
        for key, value in sorted(payload.items()):
            shape |= _collect_shape(value, f"{path}.{key}")
        return shape

    if isinstance(payload, list):
        for item in payload:
            shape |= _collect_shape(item, f"{path}[]")
        return shape

    return shape


def _read_known_shape(snapshot_path: Path) -> list[str]:
    if not snapshot_path.exists():
        return []
    payload = json.loads(snapshot_path.read_text())
    shape = payload.get("shape", [])
    if isinstance(shape, list):
        return [item for item in shape if isinstance(item, str)]
    return []


def _merge_shape_snapshot(snapshot_path: Path, name: str, observed_shape: list[str]) -> None:
    known_shape = _read_known_shape(snapshot_path)
    merged = sorted(set(known_shape) | set(observed_shape))
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps({"name": name, "shape": merged}, indent=2) + "\n")


def _collect_unknown_field_observations(
    annotation: Any,
    payload: Any,
    path: str = "$",
) -> list[UnknownFieldObservation]:
    annotation = _unwrap_annotation(annotation)

    if payload is None or annotation in {Any, object}:
        return []

    if _is_root_model(annotation):
        return _collect_unknown_field_observations(
            annotation.model_fields["root"].annotation,
            payload,
            path,
        )

    if _is_model(annotation):
        if not isinstance(payload, dict):
            return []

        known_fields: dict[str, Any] = {}
        for field_name, field in annotation.model_fields.items():
            for candidate in _field_input_names(field_name, field):
                known_fields[candidate] = field

        observations = [
            UnknownFieldObservation(
                owner_model=annotation,
                path=f"{path}.{key}",
                alias=key,
                sample_value=payload[key],
            )
            for key in sorted(payload)
            if key not in known_fields
        ]

        for key, value in payload.items():
            field = known_fields.get(key)
            if field is None:
                continue
            observations.extend(
                _collect_unknown_field_observations(
                    field.annotation,
                    value,
                    f"{path}.{key}",
                )
            )
        return observations

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in {list, tuple, set, frozenset} and args and isinstance(payload, list):
        item_type = args[0]
        nested_observations: list[UnknownFieldObservation] = []
        for item in payload:
            nested_observations.extend(
                _collect_unknown_field_observations(item_type, item, f"{path}[]")
            )
        return nested_observations

    if origin is dict:
        return []

    if origin in {UnionType, Union}:
        branch_results = [
            _collect_unknown_field_observations(branch, payload, path)
            for branch in args
            if branch is not NoneType
        ]
        if not branch_results:
            return []
        return min(branch_results, key=len)

    return []


def _apply_model_patches(
    endpoint_name: str,
    observations: list[UnknownFieldObservation],
) -> None:
    for observation in observations:
        owner_model = observation.owner_model
        file_path = inspect.getsourcefile(owner_model)
        if file_path is None:
            continue

        field_name = _normalize_field_name(observation.alias)
        patch_key = (file_path, owner_model.__name__, field_name)
        if patch_key in _PATCHED_FIELDS:
            continue

        source_path = Path(file_path)
        inserted = _insert_field_into_model(
            source_path,
            owner_model.__name__,
            field_name,
            observation.alias,
            observation.sample_value,
        )
        if not inserted:
            continue

        _PATCHED_FIELDS.add(patch_key)
        _REPORT_ROWS.append(
            {
                "endpoint": endpoint_name,
                "model": f"{owner_model.__module__}.{owner_model.__name__}",
                "path": observation.path,
                "alias": observation.alias,
                "field_name": field_name,
                "type": _infer_field_type(observation.sample_value),
                "file": str(source_path),
            }
        )

    if _REPORT_ROWS:
        EXPANSION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        EXPANSION_REPORT_PATH.write_text(json.dumps(_REPORT_ROWS, indent=2) + "\n")


def _insert_field_into_model(
    source_path: Path,
    class_name: str,
    field_name: str,
    alias: str,
    sample_value: Any,
) -> bool:
    lines = source_path.read_text().splitlines()
    class_index = _find_class_index(lines, class_name)
    if class_index is None:
        return False

    class_end = _find_class_end(lines, class_index)
    if _class_has_field(lines[class_index:class_end], field_name):
        return False

    insert_at = _find_insert_index(lines, class_index, class_end)
    rendered_field = _render_field_line(field_name, alias, sample_value)
    lines.insert(insert_at, rendered_field)
    source_path.write_text("\n".join(lines) + "\n")
    return True


def _find_class_index(lines: list[str], class_name: str) -> int | None:
    class_pattern = re.compile(rf"^class {re.escape(class_name)}\b")
    for index, line in enumerate(lines):
        if class_pattern.match(line):
            return index
    return None


def _find_class_end(lines: list[str], class_index: int) -> int:
    for index in range(class_index + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped:
            continue
        indent = len(lines[index]) - len(lines[index].lstrip())
        if indent == 0:
            return index
    return len(lines)


def _find_insert_index(lines: list[str], class_index: int, class_end: int) -> int:
    for index in range(class_index + 1, class_end):
        stripped = lines[index].lstrip()
        if stripped.startswith(("@", "def ")):
            return index
    return class_end


def _class_has_field(class_lines: list[str], field_name: str) -> bool:
    field_pattern = re.compile(rf"^\s+{re.escape(field_name)}:")
    return any(field_pattern.match(line) for line in class_lines)


def _render_field_line(field_name: str, alias: str, sample_value: Any) -> str:
    field_type = _infer_field_type(sample_value)
    if alias == field_name:
        return f"    {field_name}: {field_type} = None"
    return f'    {field_name}: {field_type} = Field(None, alias="{alias}")'


def _infer_field_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool | None"
    if isinstance(value, int):
        return "int | None"
    if isinstance(value, float):
        return "float | None"
    if isinstance(value, str):
        return "str | None"
    if isinstance(value, list):
        return "list[object] | None"
    if isinstance(value, dict):
        return "dict[str, object] | None"
    return "object | None"


def _normalize_field_name(alias: str) -> str:
    field_name = re.sub(r"(?<!^)(?=[A-Z])", "_", alias).lower()
    field_name = re.sub(r"[^0-9a-zA-Z_]", "_", field_name)
    field_name = re.sub(r"_+", "_", field_name).strip("_") or "field"
    if field_name[0].isdigit():
        field_name = f"field_{field_name}"
    if keyword.iskeyword(field_name):
        field_name = f"{field_name}_field"
    return field_name


def _unwrap_annotation(annotation: Any) -> Any:
    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            annotation = get_args(annotation)[0]
            continue
        return annotation


def _field_input_names(field_name: str, field: Any) -> set[str]:
    names = {field_name}
    if field.alias:
        names.add(field.alias)

    validation_alias = field.validation_alias
    if isinstance(validation_alias, str):
        names.add(validation_alias)
    elif isinstance(validation_alias, AliasChoices):
        for choice in validation_alias.choices:
            if isinstance(choice, str):
                names.add(choice)
    elif (
        isinstance(validation_alias, AliasPath)
        and validation_alias.path
        and isinstance(validation_alias.path[0], str)
    ):
        names.add(validation_alias.path[0])

    return names


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _is_root_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, RootModel)


def _snapshot_slug(name: str) -> str:
    return name.lower().replace("/", "_").replace("{", "").replace("}", "").replace(" ", "_")


def _format_items(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items[:40]) + (
        "\n- ..." if len(items) > 40 else ""
    )
