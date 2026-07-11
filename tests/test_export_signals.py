from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from athanasor.skills.export_signals import build_export, write_export


class ExportSignalsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self._write_yaml(
            "citrinitas/within_domain/ML/a_b.yaml",
            {
                "paper_a_id": "paper_a",
                "paper_b_id": "paper_b",
                "description": "Shared matrix-constraint stability pattern.",
                "evidence_a": "Paper A constrains the recurrent update.",
                "evidence_b": "Paper B constrains residual propagation.",
                "confidence": 4,
                "status": "pending_review",
            },
        )
        self._write_yaml(
            "rubedo/hypotheses/cluster_a_b_3.yaml",
            {
                "cluster_id": "cluster_a_b_3",
                "summary": "A benchmark could compare three stability constraints.",
                "status": "pending_review",
                "gaps": [
                    {
                        "description": "No same-backbone comparison exists.",
                        "supporting_evidence": "The cluster contains separate constraint families.",
                        "confidence": 3,
                    }
                ],
            },
        )
        self._write_yaml(
            "rubedo/prior_art/cluster_a_b_3.yaml",
            {
                "artifact_type": "rubedo_prior_art",
                "cluster_id": "cluster_a_b_3",
                "decision": "reject_novelty_claim",
                "claim_reviewed": "Spectral constraints in looped transformers.",
                "sources": [
                    {
                        "title": "Prior Art A",
                        "url": "https://arxiv.org/abs/2604.12946",
                        "finding": "Directly overlaps the claim.",
                        "impact": "direct_prior_art",
                    }
                ],
                "assessment": {
                    "novelty_result": "rejected",
                    "recommended_reframe": "Reframe as a benchmark question.",
                },
            },
        )
        self._init_git_repo()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_build_export_writes_exactly_three_staged_signals(self) -> None:
        payload = build_export(self.root)

        self.assertEqual(payload["schema_name"], "azoth-signals")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["producer"], "azoth")
        self.assertTrue(payload["producer_git_commit"])
        self.assertEqual(payload["producer_dirty_state"], "clean")
        self.assertEqual(payload["export_scope"]["max_signals"], 3)
        self.assertEqual(len(payload["signals"]), 3)
        self.assertEqual(
            {signal["signal_type"] for signal in payload["signals"]},
            {"connection_candidate", "hypothesis_candidate", "prior_art_seed"},
        )

        for signal in payload["signals"]:
            self.assertEqual(signal["source_project"], "azoth")
            self.assertEqual(signal["authority_label"], "unverified")
            self.assertEqual(signal["review_status"], "pending_review")
            self.assertIn(signal["recommended_anastomosis_label"], {"inferred", "speculative"})
            self.assertGreaterEqual(len(signal["source_artifacts"]), 1)
            self.assertGreaterEqual(len(signal["evidence"]), 1)
            for source_path in signal["source_artifacts"]:
                self.assertFalse(Path(source_path).is_absolute())
                self.assertNotIn("..", Path(source_path).parts)

    def test_write_export_persists_valid_json(self) -> None:
        output = self.root / "out" / "azoth-signals-v1.json"

        written = write_export(self.root, output)

        self.assertEqual(written, output)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["signals"]), 3)

    def _write_yaml(self, relative: str, payload: dict) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def _init_git_repo(self) -> None:
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "test fixtures"], cwd=self.root, check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
