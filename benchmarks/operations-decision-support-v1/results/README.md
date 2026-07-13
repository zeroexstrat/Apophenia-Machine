# Operations Decision Support v1 — Locked Results

This is a bounded 12-paper benchmark. Candidate validity and novelty remain human-reviewed.
The declared 5.6 Sol backend label is frozen, but provider model identity was not exposed by the runtime and is not independently verified.

- Lock manifest SHA-256: `a2e0949d46415cba71c833cd7c992ef3af4c1625432f8579b87b248d60378092`
- Execution manifest SHA-256: `a828fd5713545041dfbea41973e4596ff5c25a8084536c1d71fb207d413e9060`

| Run | Metric | Value | Numerator / denominator | Uncertainty | Result |
|---|---|---:|---:|---|---|
| model_5_6_sol | macro_f1 | 0.5103 | 33 / 66 | 0.3868–0.6212 | threshold not met |
| model_5_6_sol | unsafe_ood_assignment | undefined | 0 / 0 | undefined–undefined | undefined |
| model_5_6_sol | claim_precision | 0.9394 | 62 / 66 | 0.8543–0.9762 | threshold met |
| model_5_6_sol | reference_recall | 1.0000 | 27 / 27 | 0.8754–1.0000 | threshold met |
| model_5_6_sol | candidate_recall | 1.0000 | 27 / 27 | 0.8754–1.0000 | threshold met |
| model_5_6_sol | workload_reduction | 0.4242 | 28 / 66 | 0.3030–0.5303 | threshold not met |
| model_5_6_sol | precision_at_5 | 0.7667 | 46 / 60 | 0.6833–0.8504 | threshold met |
| model_5_6_sol | ndcg_at_10 | 0.9133 | 161.2897 / 176.5038 | 0.8752–0.9472 | threshold met |
| model_5_6_sol | evidence_support | 1.0000 | 132 / 132 | 0.9717–1.0000 | threshold met |
| model_5_6_sol | supported_items | 0.9394 | 62 / 66 | 0.8543–0.9762 | threshold met |
| model_5_6_sol | useful_items | 0.5152 | 34 / 66 | 0.3971–0.6315 | threshold not met |
| model_5_6_sol | redundancy | 0.0000 | 0 / 66 | 0.0000–0.0550 | threshold met |
| model_5_6_sol | unsupported_derived_items | undefined | 0 / 0 | undefined–undefined | undefined |
| deterministic_routing | macro_f1 | 0.0769 | 12 / 66 | 0.0417–0.1071 | threshold not met |
| deterministic_routing | unsafe_ood_assignment | undefined | 0 / 0 | undefined–undefined | undefined |
| deterministic_routing | claim_precision | undefined | 0 / 0 | undefined–undefined | undefined |
| deterministic_routing | reference_recall | 0.0000 | 0 / 27 | 0.0000–0.1246 | threshold not met |
| deterministic_routing | candidate_recall | 0.0000 | 0 / 27 | 0.0000–0.1246 | threshold not met |
| deterministic_routing | workload_reduction | 1.0000 | 66 / 66 | 1.0000–1.0000 | threshold met |
| deterministic_routing | precision_at_5 | 0.4667 | 28 / 60 | 0.3667–0.6000 | threshold not met |
| deterministic_routing | ndcg_at_10 | 0.7100 | 125.6392 / 176.5038 | 0.6183–0.7989 | threshold met |
| deterministic_routing | evidence_support | undefined | 0 / 0 | undefined–undefined | undefined |
| deterministic_routing | supported_items | undefined | 0 / 0 | undefined–undefined | undefined |
| deterministic_routing | useful_items | undefined | 0 / 0 | undefined–undefined | undefined |
| deterministic_routing | redundancy | undefined | 0 / 0 | undefined–undefined | undefined |
| deterministic_routing | unsupported_derived_items | undefined | 0 / 0 | undefined–undefined | undefined |
| all_pairs | macro_f1 | 0.1071 | 18 / 66 | 0.0714–0.1374 | threshold not met |
| all_pairs | unsafe_ood_assignment | undefined | 0 / 0 | undefined–undefined | undefined |
| all_pairs | claim_precision | undefined | 0 / 0 | undefined–undefined | undefined |
| all_pairs | reference_recall | 1.0000 | 27 / 27 | 0.8754–1.0000 | threshold met |
| all_pairs | candidate_recall | 1.0000 | 27 / 27 | 0.8754–1.0000 | threshold met |
| all_pairs | workload_reduction | 0.0000 | 0 / 66 | 0.0000–0.0000 | threshold not met |
| all_pairs | precision_at_5 | 0.4833 | 29 / 60 | 0.3000–0.6667 | threshold not met |
| all_pairs | ndcg_at_10 | 0.6559 | 114.2830 / 176.5038 | 0.5678–0.7536 | threshold met |
| all_pairs | evidence_support | undefined | 0 / 0 | undefined–undefined | undefined |
| all_pairs | supported_items | undefined | 0 / 0 | undefined–undefined | undefined |
| all_pairs | useful_items | undefined | 0 / 0 | undefined–undefined | undefined |
| all_pairs | redundancy | undefined | 0 / 0 | undefined–undefined | undefined |
| all_pairs | unsupported_derived_items | undefined | 0 / 0 | undefined–undefined | undefined |
| shared_tag | macro_f1 | 0.0769 | 12 / 66 | 0.0417–0.1071 | threshold not met |
| shared_tag | unsafe_ood_assignment | undefined | 0 / 0 | undefined–undefined | undefined |
| shared_tag | claim_precision | undefined | 0 / 0 | undefined–undefined | undefined |
| shared_tag | reference_recall | 0.0000 | 0 / 27 | 0.0000–0.1246 | threshold not met |
| shared_tag | candidate_recall | 0.0000 | 0 / 27 | 0.0000–0.1246 | threshold not met |
| shared_tag | workload_reduction | 1.0000 | 66 / 66 | 1.0000–1.0000 | threshold met |
| shared_tag | precision_at_5 | 0.4833 | 29 / 60 | 0.3000–0.6667 | threshold not met |
| shared_tag | ndcg_at_10 | 0.6559 | 114.2830 / 176.5038 | 0.5678–0.7536 | threshold met |
| shared_tag | evidence_support | undefined | 0 / 0 | undefined–undefined | undefined |
| shared_tag | supported_items | undefined | 0 / 0 | undefined–undefined | undefined |
| shared_tag | useful_items | undefined | 0 / 0 | undefined–undefined | undefined |
| shared_tag | redundancy | undefined | 0 / 0 | undefined–undefined | undefined |
| shared_tag | unsupported_derived_items | undefined | 0 / 0 | undefined–undefined | undefined |
| hash_embedding | macro_f1 | 0.1708 | 16 / 66 | 0.0974–0.2444 | threshold not met |
| hash_embedding | unsafe_ood_assignment | undefined | 0 / 0 | undefined–undefined | undefined |
| hash_embedding | claim_precision | undefined | 0 / 0 | undefined–undefined | undefined |
| hash_embedding | reference_recall | 0.0741 | 2 / 27 | 0.0206–0.2337 | threshold not met |
| hash_embedding | candidate_recall | 0.0741 | 2 / 27 | 0.0206–0.2337 | threshold not met |
| hash_embedding | workload_reduction | 0.9242 | 61 / 66 | 0.8636–0.9848 | threshold met |
| hash_embedding | precision_at_5 | 0.4333 | 26 / 60 | 0.3333–0.5667 | threshold not met |
| hash_embedding | ndcg_at_10 | 0.6971 | 123.4969 / 176.5038 | 0.6028–0.7873 | threshold met |
| hash_embedding | evidence_support | undefined | 0 / 0 | undefined–undefined | undefined |
| hash_embedding | supported_items | undefined | 0 / 0 | undefined–undefined | undefined |
| hash_embedding | useful_items | undefined | 0 / 0 | undefined–undefined | undefined |
| hash_embedding | redundancy | undefined | 0 / 0 | undefined–undefined | undefined |
| hash_embedding | unsupported_derived_items | undefined | 0 / 0 | undefined–undefined | undefined |
| current_score | macro_f1 | 0.2009 | 27 / 66 | 0.1250–0.2792 | threshold not met |
| current_score | unsafe_ood_assignment | undefined | 0 / 0 | undefined–undefined | undefined |
| current_score | claim_precision | undefined | 0 / 0 | undefined–undefined | undefined |
| current_score | reference_recall | 0.0000 | 0 / 27 | 0.0000–0.1246 | threshold not met |
| current_score | candidate_recall | 0.0000 | 0 / 27 | 0.0000–0.1246 | threshold not met |
| current_score | workload_reduction | 1.0000 | 66 / 66 | 1.0000–1.0000 | threshold met |
| current_score | precision_at_5 | 0.5667 | 34 / 60 | 0.4500–0.7000 | threshold not met |
| current_score | ndcg_at_10 | 0.9165 | 161.7546 / 176.5038 | 0.8914–0.9403 | threshold met |
| current_score | evidence_support | undefined | 0 / 0 | undefined–undefined | undefined |
| current_score | supported_items | undefined | 0 / 0 | undefined–undefined | undefined |
| current_score | useful_items | undefined | 0 / 0 | undefined–undefined | undefined |
| current_score | redundancy | undefined | 0 / 0 | undefined–undefined | undefined |
| current_score | unsupported_derived_items | undefined | 0 / 0 | undefined–undefined | undefined |
| fixed_seed_random | macro_f1 | 0.3524 | 24 / 66 | 0.2317–0.4599 | threshold not met |
| fixed_seed_random | unsafe_ood_assignment | undefined | 0 / 0 | undefined–undefined | undefined |
| fixed_seed_random | claim_precision | undefined | 0 / 0 | undefined–undefined | undefined |
| fixed_seed_random | reference_recall | 0.4815 | 13 / 27 | 0.3074–0.6601 | threshold not met |
| fixed_seed_random | candidate_recall | 0.4815 | 13 / 27 | 0.3074–0.6601 | threshold not met |
| fixed_seed_random | workload_reduction | 0.5606 | 37 / 66 | 0.4394–0.6818 | threshold met |
| fixed_seed_random | precision_at_5 | 0.3167 | 19 / 60 | 0.2000–0.4500 | threshold not met |
| fixed_seed_random | ndcg_at_10 | 0.6016 | 108.4163 / 176.5038 | 0.5088–0.7104 | threshold not met |
| fixed_seed_random | evidence_support | undefined | 0 / 0 | undefined–undefined | undefined |
| fixed_seed_random | supported_items | undefined | 0 / 0 | undefined–undefined | undefined |
| fixed_seed_random | useful_items | undefined | 0 / 0 | undefined–undefined | undefined |
| fixed_seed_random | redundancy | undefined | 0 / 0 | undefined–undefined | undefined |
| fixed_seed_random | unsupported_derived_items | undefined | 0 / 0 | undefined–undefined | undefined |

## Failure counts

- model_5_6_sol: 11 false positives; 0 false negatives; 0 ranking misses; 3 thresholds not met; 2 undefined metrics.
- deterministic_routing: 0 false positives; 27 false negatives; 9 ranking misses; 4 thresholds not met; 7 undefined metrics.
- all_pairs: 39 false positives; 0 false negatives; 9 ranking misses; 3 thresholds not met; 7 undefined metrics.
- shared_tag: 0 false positives; 27 false negatives; 9 ranking misses; 4 thresholds not met; 7 undefined metrics.
- hash_embedding: 3 false positives; 25 false negatives; 12 ranking misses; 4 thresholds not met; 7 undefined metrics.
- current_score: 0 false positives; 27 false negatives; 6 ranking misses; 4 thresholds not met; 7 undefined metrics.
- fixed_seed_random: 16 false positives; 14 false negatives; 14 ranking misses; 5 thresholds not met; 7 undefined metrics.

Missed thresholds were retained without retuning. Undefined populations were not imputed.
