from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from athanasor import cli as cli_module
from athanasor.benchmark.artifacts import SYNTHETIC_NOTICE, artifact_digest
from athanasor.benchmark.pipeline import FetchResponse
from athanasor.benchmark.scoring import synthetic_gold_commitment
from tests.test_benchmark_pipeline import BENCHMARK_ROOT, synthetic_manifest


COMMANDS = (
    "validate",
    "fetch",
    "prepare",
    "run",
    "baseline",
    "adapt",
    "lock",
    "annotations",
    "score",
    "report",
    "compare",
)


def test_benchmark_help_lists_exact_commands() -> None:
    result = CliRunner().invoke(cli_module.main, ["benchmark", "--help"])
    assert result.exit_code == 0, result.output
    for command in COMMANDS:
        assert command in result.output


@pytest.mark.parametrize(
    "command", ["validate", "fetch", "prepare", "run", "baseline", "adapt", "lock", "report"]
)
def test_generation_side_commands_have_no_gold_option(command: str) -> None:
    result = CliRunner().invoke(cli_module.main, ["benchmark", command, "--help"])
    assert result.exit_code == 0, result.output
    assert "--gold" not in result.output


def test_score_requires_explicit_external_gold() -> None:
    result = CliRunner().invoke(cli_module.main, ["benchmark", "score", "--help"])
    assert result.exit_code == 0, result.output
    assert "--gold" in result.output
    assert "required" in result.output.casefold()
    assert "--lock" in result.output
    assert "--execution-manifest" in result.output


def test_p7_cli_contracts_are_explicit_and_private_path_bound() -> None:
    runner = CliRunner()
    baseline = runner.invoke(cli_module.main, ["benchmark", "baseline", "--help"])
    assert baseline.exit_code == 0, baseline.output
    assert "--run-id" in baseline.output
    assert "--execution-manifest" in baseline.output
    adapt = runner.invoke(cli_module.main, ["benchmark", "adapt", "--help"])
    assert adapt.exit_code == 0, adapt.output
    assert "--responses-dir" in adapt.output
    assert "--provenance" in adapt.output
    lock = runner.invoke(cli_module.main, ["benchmark", "lock", "--help"])
    assert lock.exit_code == 0, lock.output
    assert "--implementation-git-sha" in lock.output
    assert "--run" in lock.output


def test_validate_public_benchmark_without_gold() -> None:
    result = CliRunner().invoke(
        cli_module.main,
        ["benchmark", "validate", "--benchmark-root", str(BENCHMARK_ROOT), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "valid"
    assert "gold" not in payload


def test_score_rejects_gold_inside_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    gold = repo / "gold.json"
    gold.write_text("{}", encoding="utf-8")
    run = tmp_path / "run.json"
    run.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(
        cli_module.main,
        [
            "benchmark",
            "score",
            "--benchmark-root",
            str(BENCHMARK_ROOT),
            "--run",
            str(run),
            "--gold",
            str(gold),
            "--output",
            str(tmp_path / "score.json"),
            "--repo-root",
            str(repo),
        ],
    )
    assert result.exit_code != 0
    assert "outside the repository" in result.output


def _response_map(manifest: dict[str, object]) -> dict[str, FetchResponse]:
    responses: dict[str, FetchResponse] = {}
    for source in manifest["sources"]:  # type: ignore[index]
        url = f"https://example.invalid/{source['paper_id']}"
        source["download_url"] = url
        source["canonical_url"] = url
        source["publication_date"] = "2026-01-01"
        source["access_date"] = "2026-07-12"
        source["license_evidence_url"] = "https://example.invalid/synthetic-license"
        responses[url] = FetchResponse(
            source["source_text"].encode("utf-8"), url, (url,), url, "application/pdf"
        )
    return responses


def test_fictional_cli_flow_is_reproducible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    benchmark = tmp_path / "benchmark"
    shutil.copytree(BENCHMARK_ROOT, benchmark)
    manifest = synthetic_manifest()
    responses = _response_map(manifest)
    manifest_path = benchmark / "synthetic" / "cli-sources.yaml"
    import yaml

    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr("athanasor.benchmark.cli.fetch_https", responses.__getitem__)
    repo = tmp_path / "repo"
    repo.mkdir()

    def execute(root: Path) -> tuple[bytes, bytes, bytes, bytes]:
        root.mkdir()
        sources = root / "sources"
        prepared = root / "prepared.json"
        run = root / "run.json"
        score = root / "score.json"
        report = root / "report.md"
        runner = CliRunner()
        commands = [
            ["benchmark", "fetch", "--benchmark-root", str(benchmark), "--source-manifest", str(manifest_path), "--source-dir", str(sources), "--repo-root", str(repo)],
            ["benchmark", "prepare", "--benchmark-root", str(benchmark), "--source-manifest", str(manifest_path), "--source-dir", str(sources), "--output", str(prepared), "--repo-root", str(repo)],
            ["benchmark", "run", "--prepared", str(prepared), "--output", str(run)],
        ]
        for command in commands:
            result = runner.invoke(cli_module.main, command)
            assert result.exit_code == 0, result.output
        run_payload = json.loads(run.read_text(encoding="utf-8"))
        gold = {
            "schema_version": 1,
            "artifact_type": "azoth_synthetic_gold",
            "benchmark_id": "operations-decision-support-v1",
            "synthetic": True,
            "notice": SYNTHETIC_NOTICE,
            "gold_pairs": [
                {
                    "pair_id": row["pair_id"],
                    "paper_a_id": row["paper_a_id"],
                    "paper_b_id": row["paper_b_id"],
                    "label": index % 4,
                }
                for index, row in enumerate(run_payload["results"])
            ],
            "freeze": {"freeze_time": "2026-07-12T00:00:00Z"},
        }
        gold_path = root / "gold.json"
        gold_path.write_text(json.dumps(gold, sort_keys=True), encoding="utf-8")
        commitment = {
            "schema_version": 1,
            "artifact_type": "azoth_synthetic_gold_commitment",
            "benchmark_id": "operations-decision-support-v1",
            "synthetic": True,
            "notice": SYNTHETIC_NOTICE,
            "commitment": synthetic_gold_commitment(gold),
        }
        (benchmark / "synthetic" / "gold-commitment.json").write_text(
            json.dumps(commitment, sort_keys=True), encoding="utf-8"
        )
        score_result = runner.invoke(
            cli_module.main,
            ["benchmark", "score", "--benchmark-root", str(benchmark), "--run", str(run), "--gold", str(gold_path), "--output", str(score), "--repo-root", str(repo)],
        )
        assert score_result.exit_code == 0, score_result.output
        report_result = runner.invoke(
            cli_module.main,
            ["benchmark", "report", "--score", str(score), "--output", str(report)],
        )
        assert report_result.exit_code == 0, report_result.output
        assert SYNTHETIC_NOTICE.encode() in report.read_bytes()
        return prepared.read_bytes(), run.read_bytes(), score.read_bytes(), report.read_bytes()

    assert execute(tmp_path / "first") == execute(tmp_path / "second")


def test_public_docs_show_isolated_flow_and_non_claim_boundary() -> None:
    benchmark_readme = (BENCHMARK_ROOT / "README.md").read_text(encoding="utf-8")
    root_readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
        encoding="utf-8"
    )
    for command in COMMANDS:
        assert f"azoth benchmark {command}" in benchmark_readme
    assert SYNTHETIC_NOTICE in benchmark_readme
    assert "P6 publishes no benchmark performance result" in root_readme
