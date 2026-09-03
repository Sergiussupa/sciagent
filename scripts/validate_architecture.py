#!/usr/bin/env python3

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent

MODULES_DIR = ROOT / "modules"
SCHEMA_PATH = ROOT / "schemas" / "module.schema.json"
LAYERS_PATH = ROOT / "architecture" / "layers.yaml"
STATUSES_PATH = ROOT / "architecture" / "statuses.yaml"


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def fail(errors):
    print("\nArchitecture validation: FAILED")
    for error in errors:
        print(f"  ERROR: {error}")
    print(f"\nTotal errors: {len(errors)}")
    return 1


def main():
    errors = []

    # ---------------------------------------------------------
    # Load architecture registries
    # ---------------------------------------------------------

    try:
        schema = load_json(SCHEMA_PATH)
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return fail([f"Invalid JSON Schema: {exc}"])

    try:
        layers_doc = load_yaml(LAYERS_PATH)
        statuses_doc = load_yaml(STATUSES_PATH)
    except Exception as exc:
        return fail([f"Cannot load architecture registry: {exc}"])

    layers = layers_doc.get("layers", [])
    statuses = statuses_doc.get("statuses", [])

    layer_ids = [item.get("id") for item in layers]
    status_ids = [item.get("id") for item in statuses]

    if len(layer_ids) != len(set(layer_ids)):
        errors.append("Duplicate layer IDs in architecture/layers.yaml")

    if len(status_ids) != len(set(status_ids)):
        errors.append("Duplicate status IDs in architecture/statuses.yaml")

    # The schema and architecture registry must describe the same universe.
    schema_layers = set(schema["properties"]["layer"]["enum"])
    schema_statuses = set(schema["properties"]["status"]["enum"])

    if schema_layers != set(layer_ids):
        errors.append(
            "Layer IDs in module.schema.json do not match architecture/layers.yaml"
        )

    if schema_statuses != set(status_ids):
        errors.append(
            "Status IDs in module.schema.json do not match architecture/statuses.yaml"
        )

    # ---------------------------------------------------------
    # Load module passports
    # ---------------------------------------------------------

    module_files = sorted(MODULES_DIR.glob("*/module.yaml"))

    if not module_files:
        errors.append("No module passports found in modules/*/module.yaml")
        return fail(errors)

    validator = Draft202012Validator(schema)

    modules = {}
    module_paths = {}

    for module_file in module_files:
        try:
            module = load_yaml(module_file)
        except Exception as exc:
            errors.append(f"{module_file}: invalid YAML: {exc}")
            continue

        schema_errors = sorted(
            validator.iter_errors(module),
            key=lambda e: list(e.absolute_path),
        )

        for error in schema_errors:
            field = ".".join(str(p) for p in error.absolute_path)
            location = field if field else "<root>"
            errors.append(
                f"{module_file}: schema error at {location}: {error.message}"
            )

        module_id = module.get("id")

        if not module_id:
            continue

        if module_id in modules:
            errors.append(
                f"Duplicate module id '{module_id}' "
                f"in {module_paths[module_id]} and {module_file}"
            )
            continue

        modules[module_id] = module
        module_paths[module_id] = module_file

        # Convention: directory name must equal module ID.
        if module_file.parent.name != module_id:
            errors.append(
                f"{module_file}: directory '{module_file.parent.name}' "
                f"must match module id '{module_id}'"
            )

    # ---------------------------------------------------------
    # Cross-module validation
    # ---------------------------------------------------------

    for module_id, module in modules.items():
        module_file = module_paths[module_id]

        layer = module.get("layer")
        if layer not in layer_ids:
            errors.append(
                f"{module_file}: unknown layer '{layer}'"
            )

        status = module.get("status")
        if status not in status_ids:
            errors.append(
                f"{module_file}: unknown status '{status}'"
            )

        for dependency in module.get("depends_on", []):
            if dependency == module_id:
                errors.append(
                    f"{module_file}: module cannot depend on itself"
                )
            elif dependency not in modules:
                errors.append(
                    f"{module_file}: depends_on references "
                    f"unknown module '{dependency}'"
                )

        implementation = module.get("implementation", {})
        path_text = implementation.get("path", "")
        expected_exists = implementation.get("exists")

        if path_text:
            implementation_path = ROOT / path_text
            actual_exists = implementation_path.exists()

            if expected_exists is True and not actual_exists:
                errors.append(
                    f"{module_file}: implementation.exists=true "
                    f"but '{path_text}' does not exist"
                )

            if expected_exists is False and actual_exists:
                errors.append(
                    f"{module_file}: implementation.exists=false "
                    f"but '{path_text}' already exists"
                )

    # ---------------------------------------------------------
    # Result
    # ---------------------------------------------------------

    if errors:
        return fail(errors)

    print("Architecture validation: PASSED")
    print(f"  Modules:  {len(modules)}")
    print(f"  Layers:   {len(layer_ids)}")
    print(f"  Statuses: {len(status_ids)}")

    print("\nModules:")
    for module_id in sorted(modules):
        module = modules[module_id]
        print(
            f"  {module_id:<24} "
            f"{module['layer']:<24} "
            f"{module['status']}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
