from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from project_pipeline.domain.budget import _MICROUNITS_PER_USD, InfracostEstimate

INFRACOST_REVIEW_REVISION = "0c473ade0fd0d725fe8f5edd719ef634d9594690"

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _money_to_microunits(value: object) -> int | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value)) * Decimal(_MICROUNITS_PER_USD)
    except (InvalidOperation, ValueError):
        return None
    if amount < 0:
        return None
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _unknown_prices(node: object) -> int:
    if isinstance(node, dict):
        count = 1 if node.get("priceNotFound") is True else 0
        return count + sum(_unknown_prices(value) for value in node.values())
    if isinstance(node, list):
        return sum(_unknown_prices(item) for item in node)
    return 0


def parse_infracost_json(payload: str | bytes) -> InfracostEstimate:
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return InfracostEstimate(
            available=False,
            complete=False,
            source_revision=INFRACOST_REVIEW_REVISION,
            reasons=("invalid_json",),
        )
    if not isinstance(data, dict):
        return InfracostEstimate(
            available=False,
            complete=False,
            source_revision=INFRACOST_REVIEW_REVISION,
            reasons=("root_not_object",),
        )
    currency = data.get("currency")
    if currency != "USD":
        return InfracostEstimate(
            available=True,
            complete=False,
            currency=str(currency) if currency is not None else None,
            source_revision=INFRACOST_REVIEW_REVISION,
            reasons=("unsupported_or_missing_currency",),
        )
    hourly = _money_to_microunits(data.get("totalHourlyCost"))
    monthly = _money_to_microunits(data.get("totalMonthlyCost"))
    monthly_usage = None
    projects = data.get("projects") if isinstance(data.get("projects"), list) else []
    if projects:
        usage_values = []
        for project in projects:
            if isinstance(project, dict):
                breakdown = project.get("breakdown")
                if isinstance(breakdown, dict):
                    converted = _money_to_microunits(breakdown.get("totalMonthlyUsageCost"))
                    if converted is not None:
                        usage_values.append(converted)
        if usage_values:
            monthly_usage = sum(usage_values)
    unknown = _unknown_prices(projects)
    reasons: list[str] = []
    if monthly is None:
        reasons.append("monthly_total_unknown")
    if unknown:
        reasons.append(f"unknown_price_components:{unknown}")
    return InfracostEstimate(
        available=True,
        complete=monthly is not None and unknown == 0,
        currency="USD",
        total_hourly_microunits=hourly,
        total_monthly_microunits=monthly,
        total_monthly_usage_microunits=monthly_usage,
        unknown_price_components=unknown,
        project_count=len(projects),
        source_revision=INFRACOST_REVIEW_REVISION,
        reasons=tuple(reasons),
    )


class InfracostAdapter:
    """Read-only external CLI adapter for IaC cost evidence; never applies infrastructure."""

    def __init__(
        self,
        *,
        executable: str = "infracost",
        runner: Runner | None = None,
        allow_external_read: bool = False,
    ) -> None:
        self.executable = executable
        self.runner = runner or self._run
        self.allow_external_read = allow_external_read

    @staticmethod
    def _run(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
            shell=False,
        )

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def build_command(self, root: Path, target: Path, output: Path) -> tuple[str, ...]:
        root = root.resolve()
        target = target.resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise ValueError("Infracost target must remain inside the project root") from error
        return (
            self.executable,
            "breakdown",
            f"--path={target}",
            "--format=json",
            f"--out-file={output}",
        )

    def estimate(self, root: Path, target: Path) -> InfracostEstimate:
        if not self.allow_external_read:
            return InfracostEstimate(
                available=False,
                complete=False,
                source_revision=INFRACOST_REVIEW_REVISION,
                reasons=("external_cost_read_not_authorized",),
            )
        if not self.available() and self.runner is self._run:
            return InfracostEstimate(
                available=False,
                complete=False,
                source_revision=INFRACOST_REVIEW_REVISION,
                reasons=("infracost_executable_unavailable",),
            )
        with tempfile.TemporaryDirectory(prefix="project-pipeline-infracost-") as temp_dir:
            output = Path(temp_dir) / "estimate.json"
            argv = self.build_command(root, target, output)
            result = self.runner(argv)
            if result.returncode != 0:
                return InfracostEstimate(
                    available=False,
                    complete=False,
                    source_revision=INFRACOST_REVIEW_REVISION,
                    reasons=(f"infracost_exit:{result.returncode}",),
                )
            if not output.exists():
                # An injected runner may place JSON on stdout; the real CLI uses --out-file.
                if result.stdout.strip():
                    return parse_infracost_json(result.stdout)
                return InfracostEstimate(
                    available=False,
                    complete=False,
                    source_revision=INFRACOST_REVIEW_REVISION,
                    reasons=("infracost_output_missing",),
                )
            return parse_infracost_json(output.read_text(encoding="utf-8"))
