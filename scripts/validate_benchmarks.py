#!/usr/bin/env python3

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent
MODULES_DIR = ROOT / "modules"
SPECS_DIR = ROOT / "benchmarks" / "specs"
SCHEMA_PATH = ROOT / "schemas" / "benchmark.schema.json"


def load_yaml(path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def repo_path(path_text):
    path = Path(path_text)

    if path.is_absolute():
        raise ValueError("path must be repository-relative")

    resolved = (ROOT / path).resolve()
    root_resolved = ROOT.resolve()

    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise ValueError("path escapes repository root")

    return resolved


def main():
    errors = []
    warnings = []

    # ---------------------------------------------------------
    # Load benchmark schema
    # ---------------------------------------------------------

    try:
        schema = load_json(SCHEMA_PATH)
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        print("Benchmark validation: FAILED")
        print("  ERROR: invalid benchmark schema: {}".format(exc))
        return 1

    validator = Draft202012Validator(schema)

    # ---------------------------------------------------------
    # Load module registry
    # ---------------------------------------------------------

    modules = {}

    for module_file in sorted(MODULES_DIR.glob("*/module.yaml")):
        try:
            module = load_yaml(module_file)
        except Exception as exc:
            errors.append(
                "{}: cannot load module: {}".format(module_file, exc)
            )
            continue

        module_id = module.get("id")

        if module_id:
            modules[module_id] = module

    # ---------------------------------------------------------
    # Load benchmark specifications
    # ---------------------------------------------------------

    benchmark_files = sorted(SPECS_DIR.glob("*/benchmark.yaml"))

    if not benchmark_files:
        errors.append(
            "No benchmark specs found in benchmarks/specs/*/benchmark.yaml"
        )

    benchmark_ids = set()
    reports = []

    for benchmark_file in benchmark_files:
        try:
            benchmark = load_yaml(benchmark_file)
        except Exception as exc:
            errors.append(
                "{}: invalid YAML: {}".format(benchmark_file, exc)
            )
            continue

        schema_errors = sorted(
            validator.iter_errors(benchmark),
            key=lambda error: list(error.absolute_path),
        )

        for error in schema_errors:
            field = ".".join(
                str(part) for part in error.absolute_path
            )
            location = field if field else "<root>"

            errors.append(
                "{}: schema error at {}: {}".format(
                    benchmark_file,
                    location,
                    error.message,
                )
            )

        benchmark_id = benchmark.get("id")
        module_id = benchmark.get("module")

        if benchmark_id:
            if benchmark_id in benchmark_ids:
                errors.append(
                    "Duplicate benchmark id '{}'".format(benchmark_id)
                )

            benchmark_ids.add(benchmark_id)

        if module_id not in modules:
            errors.append(
                "{}: references unknown module '{}'".format(
                    benchmark_file,
                    module_id,
                )
            )
            continue

        if benchmark_file.parent.name != module_id:
            errors.append(
                "{}: directory '{}' must match module '{}'".format(
                    benchmark_file,
                    benchmark_file.parent.name,
                    module_id,
                )
            )

        # -----------------------------------------------------
        # Metrics / acceptance
        # -----------------------------------------------------

        metrics = set(benchmark.get("metrics", []))
        acceptance_seen = set()

        for rule in benchmark.get("acceptance", []):
            metric = rule.get("metric")

            if metric not in metrics:
                errors.append(
                    "{}: acceptance metric '{}' is not declared "
                    "in metrics".format(
                        benchmark_file,
                        metric,
                    )
                )

            if metric in acceptance_seen:
                errors.append(
                    "{}: duplicate acceptance rule for '{}'".format(
                        benchmark_file,
                        metric,
                    )
                )

            acceptance_seen.add(metric)

        # -----------------------------------------------------
        # Fixtures / gold
        # -----------------------------------------------------

        fixture_ids = set()
        fixture_reports = []
        missing_assets = []

        for fixture in benchmark.get("fixtures", []):
            fixture_id = fixture.get("id")

            if fixture_id in fixture_ids:
                errors.append(
                    "{}: duplicate fixture id '{}'".format(
                        benchmark_file,
                        fixture_id,
                    )
                )

            fixture_ids.add(fixture_id)

            try:
                input_path = repo_path(fixture.get("input", ""))
                gold_path = repo_path(fixture.get("gold", ""))
            except ValueError as exc:
                errors.append(
                    "{}: fixture '{}': {}".format(
                        benchmark_file,
                        fixture_id,
                        exc,
                    )
                )
                continue

            input_ready = input_path.is_file()
            gold_ready = gold_path.is_file()

            if not input_ready:
                missing_assets.append(
                    "{} input".format(fixture_id)
                )

            if not gold_ready:
                missing_assets.append(
                    "{} gold".format(fixture_id)
                )

            fixture_reports.append(
                {
                    "id": fixture_id,
                    "input": input_ready,
                    "gold": gold_ready,
                }
            )

        module = modules[module_id]

        implementation_exists = (
            module.get("implementation", {}).get("exists", False)
        )

        # Fundamental SciAgent development rule:
        # implementation may not exist before benchmark assets are ready.
        if implementation_exists and missing_assets:
            errors.append(
                "{}: module '{}' implementation exists before "
                "benchmark assets are ready: {}".format(
                    benchmark_file,
                    module_id,
                    ", ".join(missing_assets),
                )
            )
        elif missing_assets:
            warnings.append(
                "{}: benchmark assets not ready: {}".format(
                    benchmark_id,
                    ", ".join(missing_assets),
                )
            )

        reports.append(
            {
                "id": benchmark_id,
                "module": module_id,
                "fixtures": fixture_reports,
                "ready": not missing_assets,
                "implemented": implementation_exists,
            }
        )

    # ---------------------------------------------------------
    # Report
    # ---------------------------------------------------------

    print("Benchmark validation")

    for report in reports:
        print()
        print(
            "  {} -> {}".format(
                report["id"],
                report["module"],
            )
        )

        for fixture in report["fixtures"]:
            print(
                "    fixture {:<16} input={} gold={}".format(
                    fixture["id"],
                    "READY" if fixture["input"] else "MISSING",
                    "READY" if fixture["gold"] else "MISSING",
                )
            )

        print(
            "    benchmark readiness: {}".format(
                "READY" if report["ready"] else "NOT READY"
            )
        )

        print(
            "    implementation: {}".format(
                "EXISTS"
                if report["implemented"]
                else "NOT STARTED"
            )
        )

    if warnings:
        print("\nReadiness warnings:")

        for warning in warnings:
            print("  WARNING: {}".format(warning))

    if errors:
        print("\nBenchmark validation: FAILED")

        for error in errors:
            print("  ERROR: {}".format(error))

        print("\nTotal errors: {}".format(len(errors)))
        return 1

    print("\nBenchmark validation: PASSED")
    print("  Specs: {}".format(len(reports)))
    print(
        "  Ready: {}".format(
            sum(1 for report in reports if report["ready"])
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
