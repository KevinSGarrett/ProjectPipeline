from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExternalRuntimeAdapter:
    name: str
    executable: str
    upstream_id: str

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def discovery(self) -> dict[str, object]:
        return {
            "name": self.name,
            "upstream_id": self.upstream_id,
            "executable": self.executable,
            "available": self.available(),
            "live_qualification_claim": False,
        }


LLAMA_CPP = ExternalRuntimeAdapter("llama.cpp", "llama-server", "UPSTREAM-040")
OLLAMA = ExternalRuntimeAdapter("Ollama", "ollama", "UPSTREAM-072")
LLAMA_SWAP = ExternalRuntimeAdapter("llama-swap", "llama-swap", "UPSTREAM-068")
PGBACKREST = ExternalRuntimeAdapter("pgBackRest", "pgbackrest", "UPSTREAM-082")
RESTIC = ExternalRuntimeAdapter("restic", "restic", "UPSTREAM-090")
TOXIPROXY = ExternalRuntimeAdapter("Toxiproxy", "toxiproxy-server", "UPSTREAM-093")


def activation_snapshot() -> list[dict[str, object]]:
    return [x.discovery() for x in (LLAMA_CPP, OLLAMA, LLAMA_SWAP, PGBACKREST, RESTIC, TOXIPROXY)]
