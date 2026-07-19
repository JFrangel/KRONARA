import json
import os
import subprocess
import sys

import pytest

from kronara.sidecar import _rag_evaluate


def test_rag_evaluate_rpc_returns_metrics_and_promotion_decision():
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {"token": "secret", "protocol_version": 1},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "rag.evaluate",
            "params": {
                "now": 10,
                "k": 1,
                "documents": [
                    {
                        "document_id": "rights",
                        "title": "Derechos",
                        "content": "Una licencia verificable autoriza el uso.",
                        "rights_mode": "owned_original",
                        "language": "es",
                        "scope": "narrative",
                        "valid_from": 0,
                        "valid_until": None,
                        "confidence": 1.0,
                    }
                ],
                "cases": [
                    {
                        "query": "licencia verificable",
                        "relevant_document_ids": ["rights"],
                    }
                ],
                "baseline": {
                    "recall_at_k": 0.5,
                    "mrr": 0.5,
                    "ndcg_at_k": 0.5,
                    "citation_precision": 0.5,
                    "redundancy_rate": 0.0,
                    "cases": 1,
                },
                "promotion_thresholds": {
                    "minimum_ndcg_lift": 0.1,
                    "minimum_citation_precision": 0.8,
                    "maximum_redundancy": 0.1,
                },
            },
        },
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "kronara.sidecar", "--token", "secret"],
        input="\n".join(json.dumps(request) for request in requests) + "\n",
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )
    response = json.loads(completed.stdout.splitlines()[1])

    assert response["result"]["evaluation"]["recall_at_k"] == 1.0
    assert response["result"]["promotion"]["promoted"] is True


def test_rag_evaluate_rpc_enforces_bounded_work():
    with pytest.raises(ValueError, match="at most 500 documents"):
        _rag_evaluate(
            {
                "now": 10,
                "k": 1,
                "documents": [{} for _ in range(501)],
                "cases": [{"query": "q", "relevant_document_ids": ["d"]}],
            }
        )

    with pytest.raises(ValueError, match="k must be between"):
        _rag_evaluate({"now": 10, "k": 0, "documents": [{}], "cases": [{}]})
