"""
Script de provisionamento de modelos ONNX para o Grimório.
Executar uma única vez: python scripts/download_models.py
"""

import os
from pathlib import Path

from optimum.onnxruntime import ORTModelForSequenceClassification
from transformers import AutoTokenizer

MODELS_DIR = Path(os.environ.get("GRIMOIRE_ONNX_MODEL_PATH", "./backend/models")).resolve()
MODEL_HF_ID = "BAAI/bge-reranker-v2-m3"
MODEL_LOCAL_NAME = "bge-reranker-v2-m3-onnx"


def download_and_export() -> None:
    target = MODELS_DIR / MODEL_LOCAL_NAME
    if target.exists():
        print(f"Modelo já presente em {target}. Pulando download.")
        return
    target.mkdir(parents=True, exist_ok=True)
    print(f"Baixando e convertendo {MODEL_HF_ID} para ONNX...")
    print("Isso pode levar alguns minutos na primeira execução.")
    model = ORTModelForSequenceClassification.from_pretrained(MODEL_HF_ID, export=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_HF_ID)
    model.save_pretrained(str(target))
    tokenizer.save_pretrained(str(target))
    print(f"Modelo salvo em: {target}")


if __name__ == "__main__":
    download_and_export()
