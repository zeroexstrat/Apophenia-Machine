# When a plausible gap fails prior-art review

This is a public process case, not a new research finding. It reconstructs one
candidate-to-decision transition from sanitized state and public primary sources;
it does not distribute the underlying runtime records.

## Candidate, not finding

A generated gap proposed that spectral constraints used to stabilize iterative
dynamics had not been applied to transformer-based looped architectures. The system
stored that premise as `pending_review`, not as a finding. Its suggested intervention
was to constrain recurrent transformer dynamics and measure stability across deeper
unrolling.

That distinction is the central control: a plausible analogy can justify review, but
it cannot establish an absence in the literature.

## Why review was mandatory

The candidate joined evidence already present in a small cluster: parameter-shared
iteration can increase effective depth, while spectral or geometric constraints can
stabilize repeated updates. The analogy was structurally coherent. The associated
novelty checklist nevertheless recorded that an external prior-art search had not
been run.

Azoth's generated confidence therefore described the candidate's internal evidence,
not novelty confidence. Scientific validity and novelty remain human-reviewed.

## Primary-source contradiction

Primary sources contradicted the candidate's absence premise:

- [Parcae: Scaling Laws For Stable Looped Language Models](https://arxiv.org/html/2604.12946v1)
  formulates looping as residual-stream dynamics and constrains a spectral
  parameterization to prevent state explosion in looped layers.
- [Stabilizing Recurrent Dynamics for Test-Time Scalable Latent Reasoning in Looped Language Models (STARS)](https://arxiv.org/html/2605.26733v1)
  applies Jacobian spectral-radius regularization with random loop sampling to
  encourage asymptotically stable recurrent reasoning dynamics.
- [CART: Context-Anchored Recurrent Transformer](https://arxiv.org/abs/2606.01495)
  reuses a shared core block and reports a learned linear time-invariant gate whose
  spectral radius stays below one across its fully trained configurations.

Related work strengthens the comparison space without being needed for the direct
rejection. [Residual scaling for looped transformers](https://arxiv.org/html/2606.18524)
derives loop-aware scaling for correlated, weight-tied updates.
[Training Transformers with Enforced Lipschitz Constants](https://arxiv.org/abs/2507.13338)
benchmarks norm-constrained transformer training, while
[The Lipschitz Constant of Self-Attention](https://proceedings.mlr.press/v139/kim21i.html)
provides foundational analysis of Lipschitz self-attention.

This source set is sufficient to reject the specific claim that spectral or
equivalent stability constraints had not been applied to looped or recurrent
transformers. It is not a literature-wide novelty proof.

## Human decision: reject the novelty claim

The human decision was `rejected`. The candidate did not remain simultaneously
pending or promoted, and the reviewed evidence fingerprint was retained so the same
claim/evidence packet could not silently resurface as new.

The rejection is a useful system result: the pipeline preserved an initially
plausible candidate, exposed the missing prior-art step, accepted contradictory
primary evidence, and recorded a terminal review state.

## Reframe: controlled comparison and replication

The defensible next question is comparative rather than novel: under one controlled
looped-transformer backbone, how do Parcae-style spectral parameterization,
STARS-style Jacobian regularization, CART-style learned linear gating, and loop-aware
residual scaling differ?

The smallest measurable replication and comparison would hold the backbone, data,
parameter count, optimizer, token budget, loop depths, evaluation set, and random
seeds fixed. It would measure:

- divergence or loss-spike events;
- hidden-state norm and estimated Jacobian or gate spectral growth;
- validation loss and task quality at each loop depth;
- training and inference cost; and
- compute-normalized performance across constraint families.

Start with three seeds and the smallest training slice that can expose instability.
Stop if the common baseline cannot be reproduced or if the slice never produces a
measurable stability difference. No such experiment was run as part of this case,
and the proposed comparison has no claimed novelty.

## What this case demonstrates

- Generated artifacts remain candidates until an explicit human decision.
- Evidence traceability can support a useful candidate without supporting novelty.
- Primary-source contradiction is a successful outcome, not a pipeline failure.
- A rejected premise can be reframed into a smaller replication question without
  preserving the rejected novelty language.

## Limits

This narrative demonstrates review-state handling for one historical case. It does
not measure the current system's discovery rate, prove literature-search
completeness, validate any stability method, or establish that the proposed
comparison is scientifically useful. Those judgments require separate evidence and
human review.
