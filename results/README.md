# Experiment results

Saved outputs from the training and evaluation notebooks. Keep the distinction between automated format/numerical checks and independently judged answer correctness.

| Files | Experiment |
| --- | --- |
| `pilot_mcqs.csv`, `pilot_summary.csv` | Initial Qwen model-size comparison and generated questions. |
| `eval_base7b_pilot30.csv` | Base 7B outputs for the 30-item pilot. |
| `eval_ft7b_pilot30.csv`, `eval_ft7b_all90.csv` | Fine-tuned 7B outputs for the pilot and expanded set. |
| `summary_7b.csv` | Aggregated automated checks and difficulty matching. |
| `results.csv`, `test_predictions.csv` | Earlier FLAN-T5 baseline and fine-tuning outputs. |
| `results_decoding.csv`, `test_predictions_decoding.csv` | Decoding-strategy comparisons and predictions. |

The preliminary model comparison uses small samples and AI-assisted grading. It does not establish that fine-tuning outperforms the base 7B model. Automatic verification pass rates are not equivalent to human-verified correctness. Original CSV artifacts are retained without altering their recorded values.

See [evaluation methodology and limitations](../adaptiveiq/docs/ML_EVALUATION.md), [training notebooks](../code/README.md), and [adaptive-engine simulations](../adaptiveiq/backend/evaluation/results/).
