# P9 Release and Deployment Design

**Task:** P9-T1 — `v0.2.0`, GitHub metadata, website case study, and deployment

**Status:** Approved design for implementation planning

**Date:** 2026-07-13

## 1. Objective

Publish the verified P8 tree as the GitHub-only `v0.2.0` release, then align the
public GitHub repository and `0xstrategies.com` portfolio with the same bounded,
source-backed engineering narrative. The release and site must expose the
project's reproducible workflow, measured benchmark evidence, honest misses,
human authority boundary, and prior-art rejection case without publishing
private benchmark material or implying external scientific validity.

P9 is complete only when the package installs independently, GitHub's hosted
state is verified, the portfolio deployment is verified on desktop and mobile,
and every public surface agrees on scope and limitations.

## 2. Starting state and repositories

### Apophenia Machine

- Authoritative checkout: the current durable Apophenia Machine feature checkout
- Starting branch and SHA: local `main` at
  `bbf17c56b0a0d36a377f87a009869ff9a209cc5c`
- Hosted `origin/main` starts at P7 SHA
  `ea9ed167c743ee8c25eb65804828a9ebf481aec0`; pushing P9 will also publish the
  five already-reviewed P8 commits.
- Package version starts at `0.1.3` in `pyproject.toml`.
- GitHub has no tags or releases.
- The existing `hardening` workflow runs on Python 3.10, 3.11, and 3.12.
- P8's public evidence source is
  `benchmarks/operations-decision-support-v1/results/locked-comparison.json`.

### Portfolio

- Checkout: an operator-provided clone of private repository
  `zeroexstrat/0xstrategies`
- Repository: private `zeroexstrat/0xstrategies`, clean `main`.
- Cloudflare Pages deploys from pushes to `main`.
- `index.html` and `resume.html` are self-contained bundled pages with JSON
  template payloads; they must not be replaced wholesale or converted to a new
  frontend stack in P9.
- `writing/azoth.html` is the reflective essay and remains distinct from the new
  recruiter-facing technical case study.

## 3. Scope

### In scope

- Set the package version to `0.2.0` from the single authoritative version in
  `pyproject.toml` and update every pinned release reference to match it.
- Add a changelog and executable release audit.
- Add an honest CI badge and ensure hosted CI verifies both wheel and sdist
  installation outside the checkout on Python 3.10, 3.11, and 3.12.
- Build release assets from the exact accepted commit, compute SHA-256 checksums,
  create immutable tag `v0.2.0`, and publish a GitHub release with the wheel,
  sdist, and checksum file.
- Update GitHub description, homepage, and topics after the release and site are
  live.
- Add one standalone recruiter-facing portfolio case study.
- Replace unmeasured pilot-era homepage and resume claims with locked P7 evidence.
- Add at most one benchmark-evidence bullet to the resume and publish a matching
  PDF.
- Preserve the reflective Azoth essay, adding only a contextual link to the
  technical case study if needed for navigation.
- Add executable claim/link audits for both repositories.
- Verify local desktop/mobile rendering, all public links, Cloudflare deployment,
  GitHub release assets, remote commit/tag identity, and hosted CI.

### Out of scope

- PyPI publication.
- New benchmark runs, label changes, metric changes, threshold changes, or model
  comparisons.
- Changes to P5-P7 frozen artifacts other than reading them as evidence.
- Claims of scientific validity, novelty, external validity, provider model
  identity, or production effectiveness.
- A portfolio redesign, framework migration, new visual identity, or rewrite of
  the reflective essay.
- Additional resume metrics or multiple new Azoth resume bullets.

## 4. Release architecture

### 4.1 One version source

`pyproject.toml` remains the only package-version authority. Release audits read
that value and require all tag-shaped install references, changelog headings,
release evidence, and artifact metadata to resolve to `0.2.0`. No second Python
constant is introduced.

### 4.2 Release evidence contract

Add a small committed release evidence document that records:

- version `0.2.0`;
- supported Python versions 3.10, 3.11, and 3.12;
- benchmark ID `operations-decision-support-v1`;
- SHA-256 of `locked-comparison.json`;
- the 12-paper / 66-pair evaluation scope;
- the exact subset of metrics used on the portfolio;
- the three missed targets and two undefined populations;
- the human-validity, novelty, and provider-identity limitations;
- canonical repository, case-study, and release URLs.

The release audit validates this document against `pyproject.toml` and
`locked-comparison.json`. It fails closed on missing metrics, altered numerator or
denominator values, omitted misses, or softened limitations.

Artifact hashes are not committed into this evidence document because wheel and
sdist archives contain build metadata that may vary across rebuilds. The exact
accepted release assets receive a generated `SHA256SUMS.txt`, and that file is
uploaded beside them in the GitHub release.

### 4.3 Artifact verification

The release build produces exactly:

- `azoth-0.2.0-py3-none-any.whl`;
- `azoth-0.2.0.tar.gz`;
- `SHA256SUMS.txt`.

Verification installs the wheel and sdist separately into fresh environments for
Python 3.10, 3.11, and 3.12, outside the repository. Each installation must:

- import `athanasor` without resolving into the checkout;
- report package metadata version `0.2.0`;
- expose the `azoth` console script;
- initialize a new workspace;
- ingest the fictional five-minute demo input;
- validate the workspace and pass Vigil.

The existing wheel checker is extended or wrapped rather than replaced. The
hosted hardening workflow runs the same release-artifact verifier so local and
remote acceptance use the same contract.

### 4.4 Publication order

Publication is deliberately staged:

1. Verify and commit the P9 release candidate on a feature branch.
2. Fast-forward local `main`, rerun the complete acceptance bundle, and push
   `main`.
3. Wait for the exact pushed SHA's Python 3.10-3.12 hardening run to pass.
4. Build assets from a fresh clone of that exact remote SHA and rerun artifact
   verification.
5. Create annotated tag `v0.2.0` at that SHA and push the tag.
6. Create the GitHub release with release notes, wheel, sdist, and checksums.
7. Verify release URL, tag target, asset names, asset digests, and installability
   of assets downloaded from GitHub.
8. Publish and verify the portfolio.
9. Set GitHub homepage to the live technical case-study URL and update topics.

The tag is never moved or reused. If a defect is found after publication, the
release remains immutable and remediation uses a new patch version.

## 5. Public repository narrative

### 5.1 README and changelog

The README keeps the P8 five-minute demo and exact 13-row benchmark table. P9 adds:

- the hardening workflow badge;
- a stable `v0.2.0` installation example;
- a release link after the tag exists;
- no new performance claim beyond the locked comparison.

`CHANGELOG.md` documents the public baseline, wheel initialization, frozen
benchmark, locked evaluation, rejection/reframe case, and release hardening. It
states the benchmark misses and limitations rather than presenting `v0.2.0` as a
scientific validation milestone.

### 5.2 GitHub metadata

Keep the current professional description unless the executable metadata audit
shows it conflicts with the final site. Set:

- homepage: `https://0xstrategies.com/case-studies/apophenia-machine.html`;
- topics: `python`, `cli`, `research-automation`, `operations-research`,
  `human-in-the-loop`, `knowledge-management`, and `evidence`.

Metadata is read back through GitHub after mutation. The repository must remain
public with `main` as its default branch.

### 5.3 GitHub release notes

Release notes lead with the independently installable local workflow and include:

- supported Python versions;
- wheel and sdist verification statement;
- exact suite scope;
- a compact table containing both successful and missed metrics;
- explicit undefined populations;
- the human review and provider-identity limitations;
- the prior-art rejection/reframe case;
- artifact checksum instructions.

The notes do not describe generated candidates as discoveries or confirmed
findings.

## 6. Portfolio architecture

### 6.1 Evidence manifest

Add `assets/data/apophenia-v0.2.0.json` to the portfolio repository. It is a
public-only projection of the release evidence document and contains:

- version and release URL;
- benchmark ID and locked-comparison digest;
- 12-paper / 66-pair scope;
- selected exact metrics with numerator, denominator, interval, and threshold
  result;
- missed and undefined metric names;
- human-review, external-validity, and provider-identity limitations;
- repository and case-study source URLs.

The portfolio audit uses this manifest as its local source of truth. No gold
labels, rationales, pair-level results, private paths, raw runs, or provider
secrets are copied into the site.

### 6.2 Technical case study

Create `case-studies/apophenia-machine.html` as a plain static page using the
existing `assets/portfolio.css` design vocabulary. It is recruiter-facing and
answers, in order:

1. What operational research problem the system addresses.
2. What was built: CLI stages, schemas, deterministic fallbacks, gates, session
   durability, packaging, and CI.
3. How the 12-paper / 66-pair benchmark was frozen and human-adjudicated.
4. What the locked evaluation measured, including exact successes, misses, and
   undefined populations.
5. How the looped-transformer candidate was rejected against primary-source
   prior art and reframed without resurrecting the novelty claim.
6. What engineering decisions demonstrate judgment: clean public lineage,
   private/public boundary, fail-closed audits, installed-wheel verification, and
   human authority.
7. What the evidence does not establish.
8. Where to inspect the repository, release, benchmark report, and reflective
   essay.

The page may highlight a compact subset of metrics, but it must include at least
one met target and every missed or undefined category in text or table form.

### 6.3 Homepage

Keep the current recruiter-first hero and visual identity. The Apophenia Machine
system card is revised so it:

- links first to the technical case study;
- links separately to GitHub and the reflective essay;
- replaces the unmeasured 57/54/91/5 pilot inventory with the locked 12-paper /
  66-pair benchmark;
- names at least one exact strength and one exact miss;
- says candidates remain human-reviewed.

P9 does not add a new homepage section or promote Azoth above the existing
operations-first positioning.

### 6.4 Resume and PDF

The HTML resume, maintained Markdown source, and downloadable PDF must agree.
Keep the existing pipeline and prior-art bullets. Replace the pilot-count bullet
with one benchmark-evidence bullet; do not add a fourth Azoth bullet. The new
bullet reports exact scope and a balanced result, including a miss, rather than a
string of favorable percentages.

Publish the revised PDF under a new versioned filename and update the HTML link.
Render every PDF page and inspect for clipping, overflow, broken links, missing
glyphs, or unintended pagination before replacing the public resume link.

### 6.5 Reflective essay

Preserve `writing/azoth.html` as the reflective, authorial account. P9 may add one
short navigation line linking to the measured technical case study. It does not
rewrite the essay into documentation or retrofit benchmark statistics throughout
the prose.

### 6.6 Bundled-page handling

`index.html` and `resume.html` remain bundled pages. A deterministic maintenance
script extracts the JSON template payload, applies exact old-to-new copy and link
replacements, serializes valid JSON, and refuses to run if an expected source
fragment is absent or appears more than once. Tests exercise the transformer on
temporary copies before it mutates the tracked pages.

This avoids manual escaping errors and prevents a broad bundle or visual-system
rewrite. The script is not needed at runtime.

## 7. Audits and tests

### Apophenia Machine

Add tests before implementation for:

- version and pinned-reference agreement;
- changelog version and scope;
- release evidence fidelity to the locked comparison;
- required misses, undefined populations, and limitation language;
- wheel and sdist filenames and metadata;
- installation from both artifact types outside the checkout;
- CI invoking the same release-artifact verifier;
- README badge and stable install/release links.

The final repository acceptance bundle includes the full test suite, every
maintained check script, benchmark protocol audit in public and private modes,
public narrative audit, public-tree audit, hardening audit, compileall, diff
checks, Python 3.10-3.12 artifact smoke tests, fresh-clone verification, and all
seven Vigil gates.

### Portfolio

Add tests before content changes for:

- evidence-manifest schema and exact values;
- case-study, homepage, resume, PDF source, and essay navigation agreement;
- removal of the exact pilot-inventory wording from public HTML;
- at most one benchmark-evidence resume bullet;
- required limitation language;
- local internal-link resolution across every tracked HTML file;
- HTTPS on new external links;
- absence of absolute local paths, employee IDs, internal email addresses,
  private benchmark paths, raw-run references, and bundle error overlays;
- deterministic bundled-template transformation and refusal behavior.

Browser verification covers the homepage, technical case study, resume, and
reflective essay at desktop and mobile widths. It checks visible content,
navigation, console errors, and horizontal overflow.

## 8. Failure handling and rollback

- If release-candidate tests fail, do not push `main` or create a tag.
- If hosted CI fails, fix on the feature branch or a new commit and repeat the
  exact-SHA gate; do not tag the failed SHA.
- If fresh-clone release assets differ in metadata or fail installation, discard
  them and investigate before publication.
- If tag creation succeeds but GitHub release creation fails, retain the
  immutable tag, fix the release transaction, and publish assets against that
  exact tag.
- If the portfolio deployment fails after the release is live, revert only the
  portfolio commit and redeploy; do not alter the release tag.
- If Cloudflare serves stale content, use cache-busted production requests and
  deployment-SHA checks before changing source again.
- Never weaken an audit, omit a miss, or convert an undefined metric to zero to
  make P9 pass.

## 9. Acceptance criteria

P9-T1 is complete only when all of the following are proven from current state:

1. Local and remote `main` identify the accepted P9 commit.
2. The exact remote SHA has green Python 3.10, 3.11, and 3.12 hardening jobs.
3. Tag `v0.2.0` points to that exact SHA and is not mutable.
4. The GitHub release exposes the wheel, sdist, and checksum file.
5. Downloaded release assets pass independent installation and smoke tests on
   Python 3.10, 3.11, and 3.12.
6. GitHub description, homepage, topics, default branch, and public visibility
   match this design.
7. The live homepage, technical case study, resume, PDF, and reflective essay are
   reachable and mutually consistent.
8. Desktop and mobile production checks show no broken links, console errors,
   visible bundle overlays, clipping, or horizontal overflow.
9. Public claims match the release evidence manifest and preserve every scope,
   human-authority, external-validity, and provider-identity limitation.
10. No private benchmark material, local absolute path, pilot runtime artifact,
    or unsupported performance claim appears in either public surface.
11. The P9 roadmap and session ledgers record exact SHAs, CI run, release URL,
    deployment proof, test totals, and the truthful final project state.
12. Vigil `verify` and `close` pass on the committed Apophenia Machine tree.
