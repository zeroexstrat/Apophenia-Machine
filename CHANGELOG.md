# Changelog

All notable public changes to Azoth are documented here.

## [0.2.0] - 2026-07-13

### Added

- A clean public baseline for a local, human-gated research-operations pipeline.
- Installed-workspace initialization with immutable schemas and mutable user-owned state.
- A frozen 12-paper, 66-pair benchmark protocol and locked results bound to a public digest.
- A documented prior-art rejection and reframe case showing the human authority boundary.
- Release evidence, public-tree audits, and wheel/source-distribution install checks.

### Compatibility

- Python 3.10, 3.11, and 3.12.
- GitHub Release distribution only; this release is not published on PyPI.

### Evaluation limits

- The locked suite met claim precision, reference recall, candidate recall, ranking,
  evidence-support, supported-item, and redundancy targets.
- It missed `macro_f1`, `workload_reduction`, and `useful_items`.
- `unsafe_ood_assignment` and `unsupported_derived_items` are undefined because
  their eligible denominators were zero.
- The single suite does not establish external validity or literature-wide novelty.
- Validity and novelty remain human-reviewed. The frozen `5.6 Sol` backend label
  does not expose provider model identity, so that identity is not independently verified.

[0.2.0]: https://github.com/zeroexstrat/Apophenia-Machine/releases/tag/v0.2.0
