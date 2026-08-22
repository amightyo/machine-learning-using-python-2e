# RAG Evaluation Canvas

| Component | Question / Metric |
|---|---|
| User task | |
| Corpus provenance | |
| Gold evidence | |
| Chunking strategy | |
| Embedding model | |
| Retrieval top-k | |
| Recall@k | |
| Precision@k | |
| Reranking | |
| Answer correctness | |
| Claim-level groundedness | |
| Citation support | |
| Abstention quality | |
| Unsupported claims | |
| Robustness | |
| Latency | |
| Cost | |
| Security/prompt injection | |
| Reproducibility | |

## Failure localization

When an answer is wrong, classify the failure:

1. evidence absent from corpus;
2. chunking failure;
3. embedding/retrieval failure;
4. ranking failure;
5. context construction failure;
6. generation ignored evidence;
7. generation misinterpreted evidence;
8. unsupported synthesis;
9. citation mismatch;
10. evaluation ambiguity.
