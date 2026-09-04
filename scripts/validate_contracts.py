#!/usr/bin/env python3

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT / "contracts"


def load_yaml(path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():

    errors = []
    contracts = []

    for contract_file in sorted(CONTRACTS_DIR.glob("*/contract.yaml")):

        contract_dir = contract_file.parent

        try:
            contract = load_yaml(contract_file)
        except Exception as exc:
            errors.append(
                f"{contract_file}: invalid yaml: {exc}"
            )
            continue


        schema_file = ROOT / contract["schema"]


        if not schema_file.exists():
            errors.append(
                f"{contract_file}: missing schema {schema_file}"
            )
            continue


        try:
            schema = load_json(schema_file)
            Draft202012Validator.check_schema(schema)

        except Exception as exc:
            errors.append(
                f"{schema_file}: invalid json schema: {exc}"
            )


        contracts.append(
            {
                "id": contract["id"],
                "name": contract["name"],
                "version": contract["version"],
                "schema": contract["schema"]
            }
        )


    print("Contract validation")

    for contract in contracts:
        print(
            "  {:<25} {}@{}".format(
                contract["id"],
                contract["name"],
                contract["version"]
            )
        )


    if errors:

        print("\nFAILED")

        for error in errors:
            print(" ERROR:", error)

        return 1


    print("\nContract validation PASSED")
    print("  Contracts:", len(contracts))

    return 0



if __name__ == "__main__":
    sys.exit(main())
