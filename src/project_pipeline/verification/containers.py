from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

PGVECTOR_IMAGE = "pgvector/pgvector:pg16"


def docker_executable() -> str | None:
    return shutil.which("docker")


def docker_engine_ready(*, timeout_s: float = 15.0) -> dict[str, Any]:
    executable = docker_executable()
    if executable is None:
        return {"ready": False, "reason": "DOCKER_CLI_MISSING", "executable": None}
    try:
        result = subprocess.run(
            [executable, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "ready": False,
            "reason": "DOCKER_ENGINE_UNREACHABLE",
            "executable": executable,
            "detail": str(error),
        }
    version = (result.stdout or "").strip()
    if result.returncode != 0 or not version:
        return {
            "ready": False,
            "reason": "DOCKER_ENGINE_NOT_RUNNING",
            "executable": executable,
            "stderr": (result.stderr or "")[:500],
        }
    return {
        "ready": True,
        "reason": "DOCKER_ENGINE_READY",
        "executable": executable,
        "version": version,
    }


def _run_docker(
    args: list[str],
    *,
    timeout_s: float = 60.0,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    executable = docker_executable()
    if executable is None:
        raise RuntimeError("docker CLI is not installed")
    return subprocess.run(
        [executable, *args],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
        shell=False,
        input=stdin,
    )


class PostgresVectorContainer:
    """Disposable pgvector container governed through the local Docker engine."""

    def __init__(self, *, image: str = PGVECTOR_IMAGE, name: str | None = None) -> None:
        self.image = image
        self.name = name or f"pp-c16-pgvector-{uuid.uuid4().hex[:12]}"
        self.db_auth = "local-fixture-value"
        self.database = "pp"

    @property
    def dsn(self) -> str:
        port = self.published_port()
        return f"postgresql://postgres:{self.db_auth}@127.0.0.1:{port}/{self.database}"

    def start(self) -> None:
        inspect = _run_docker(["image", "inspect", "-f", "{{.Id}}", self.image], timeout_s=20.0)
        if inspect.returncode != 0:
            pulled = _run_docker(["pull", self.image], timeout_s=90.0)
            if pulled.returncode != 0:
                raise RuntimeError(pulled.stderr.strip() or "docker pull failed")
        created = _run_docker(
            [
                "run",
                "-d",
                "--name",
                self.name,
                "-e",
                f"POSTGRES_PASSWORD={self.db_auth}",
                "-e",
                f"POSTGRES_DB={self.database}",
                "-p",
                "127.0.0.1::5432",
                self.image,
            ],
            timeout_s=90.0,
        )
        if created.returncode != 0:
            raise RuntimeError(created.stderr.strip() or "docker run failed")
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            ready = _run_docker(
                ["exec", self.name, "pg_isready", "-U", "postgres", "-d", self.database],
                timeout_s=10.0,
            )
            if ready.returncode == 0:
                return
            time.sleep(0.5)
        raise RuntimeError("pgvector container did not become ready")

    def published_port(self) -> int:
        result = _run_docker(["port", self.name, "5432/tcp"], timeout_s=15.0)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "docker port failed")
        line = (result.stdout or "").strip().splitlines()[0]
        return int(line.rsplit(":", 1)[1])

    def inspect_identity(self) -> dict[str, str]:
        result = _run_docker(
            ["inspect", "-f", "{{.Id}}|{{.Image}}|{{.Config.Image}}", self.name],
            timeout_s=15.0,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "docker inspect failed")
        container_id, image_id, image_name = result.stdout.strip().split("|", 2)
        return {
            "container_id": container_id,
            "image_id": image_id,
            "image_name": image_name,
            "requested_image": self.image,
        }

    def exec_sql(self, sql: str) -> str:
        result = _run_docker(
            [
                "exec",
                "-i",
                self.name,
                "psql",
                "-U",
                "postgres",
                "-d",
                self.database,
                "-v",
                "ON_ERROR_STOP=1",
                "-q",
            ],
            timeout_s=60.0,
            stdin=sql,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "psql failed")
        return result.stdout

    def kill(self) -> None:
        result = _run_docker(["kill", self.name], timeout_s=30.0)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "docker kill failed")

    def resume(self) -> None:
        result = _run_docker(["start", self.name], timeout_s=30.0)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "docker start failed")
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            ready = _run_docker(
                ["exec", self.name, "pg_isready", "-U", "postgres", "-d", self.database],
                timeout_s=10.0,
            )
            if ready.returncode == 0:
                return
            time.sleep(0.5)
        raise RuntimeError("pgvector container did not recover after kill")

    def remove(self) -> None:
        _run_docker(["rm", "-f", self.name], timeout_s=30.0)


@contextmanager
def postgres_vector_container() -> Iterator[PostgresVectorContainer]:
    probe = docker_engine_ready()
    if not probe["ready"]:
        raise RuntimeError(json.dumps(probe))
    container = PostgresVectorContainer()
    try:
        container.start()
        yield container
    finally:
        container.remove()
