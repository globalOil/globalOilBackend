#!/usr/bin/env python3
"""Run resumable physical-result API shards without overloading local Docker."""
import getpass
import os
import subprocess
import sys
import argparse
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ARTIFACTS = SCRIPT_DIR.parent / "outputs" / "migracion_historica_global_oil"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--password-env",
        default="DATAIA_IMPORT_PASSWORD",
        help="Nombre de la variable de entorno que contiene la contraseña.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="URL de la API local; debe coincidir con la usada por la ETL principal.",
    )
    parser.add_argument(
        "--email",
        default="admin@globaloil.local",
        help="Correo del administrador usado por toda la ETL.",
    )
    args = parser.parse_args()

    password = os.environ.get(args.password_env) or getpass.getpass("Contraseña del administrador local: ")
    if not password:
        raise SystemExit("No se recibió contraseña.")
    environment = os.environ.copy()
    environment[args.password_env] = password
    logs = ARTIFACTS / "reports" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    failures = []
    for shard in range(4):
        command = [
            sys.executable, str(SCRIPT_DIR / "submit_compound_results_via_api.py"),
            "--artifacts", str(ARTIFACTS),
            "--sample-test-map", str(ARTIFACTS / "staging" / "oa_pruebas_muestra.json"),
            "--payload-file", "api_result_payloads_physical.jsonl",
            "--report-file", f"carga_api_resultados_fisicos_forms_shard{shard}.json",
            "--base-url", args.base_url,
            "--email", args.email,
            "--password-env", args.password_env,
            "--apply", "--resume",
            "--batch-shard-count", "4", "--batch-shard-index", str(shard),
        ]
        # Four simultaneous requests were fast but could exhaust a small
        # Docker Desktop VM during a full historical import.  Each shard has
        # an independent checkpoint, so sequential execution remains fully
        # resumable while keeping the database stable.
        stdout = (logs / f"physical_shard{shard}.out.log").open("w", encoding="utf-8")
        stderr = (logs / f"physical_shard{shard}.err.log").open("w", encoding="utf-8")
        child = subprocess.Popen(command, cwd=SCRIPT_DIR, env=environment, stdout=stdout, stderr=stderr)
        status = child.wait()
        stdout.close()
        stderr.close()
        print(f"shard={shard} exit={status}", flush=True)
        if status:
            failures.append(shard)
            break
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
