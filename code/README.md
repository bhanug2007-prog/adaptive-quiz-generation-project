# Model training and experiments

The application uses Qwen2.5-7B; earlier FLAN-T5 experiments are retained to show the model-selection process. Notebook outputs and CSVs are experiment artifacts, not production accuracy guarantees.

## Main model workflow

| Order | Notebook | Purpose |
| --- | --- | --- |
| 1 | [Pilot model comparison](pilot_model_check.ipynb) | Explore candidate model sizes and generated questions. |
| 2 | [Qwen fine-tuning](finetune_qwen7b_unsloth.ipynb) | Train LoRA adapters with Unsloth and evaluate generated MCQs. |
| 3 | [GGUF conversion](convert_7b_to_gguf_kaggle.ipynb) | Prepare the trained model for llama.cpp inference. |
| 4 | [Fine-tuned topic checks](test_finetuned_7b_topics.ipynb) | Inspect behavior across topics. |
| 5 | [New-topic checks](test_new_topics_kaggle.ipynb) | Probe generalization to additional topics. |

## Earlier baselines and helpers

- [FLAN-T5 fine-tuning](finetune_flan_t5_kaggle.ipynb): earlier sequence-to-sequence baseline.
- [Decoding comparison](reevaluate_decoding_kaggle.ipynb): decoding-strategy experiments.
- [Math-check helper](mathcheck.py) and [its checks](test_mathcheck.py): experiment-side numerical validation. The application maintains its own validator under `adaptiveiq/backend/app/validators/`.

## Reproduction notes

The notebooks target hosted notebook environments such as Kaggle. Review each notebook's installation cells, input paths, compute requirements and output directories before running. Supply credentials through the environment's secrets mechanism. The [dataset archive](../btech_mcq_dataset_clean.zip) is retained at the repository root; model weights are distributed separately and excluded from Git.

See the [results index](../results/README.md) and [evaluation methodology](../adaptiveiq/docs/ML_EVALUATION.md) for interpretation and limitations.
