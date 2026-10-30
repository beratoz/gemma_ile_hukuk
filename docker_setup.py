"""Explicit first-run preparation; downloads E5 only, never Gemma."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys

MODEL_ID = "intfloat/multilingual-e5-base"
REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"
MODEL_FILES = [
    "1_Pooling/config.json", "config.json", "model.safetensors", "modules.json",
    "sentence_bert_config.json", "sentencepiece.bpe.model", "special_tokens_map.json",
    "tokenizer.json", "tokenizer_config.json",
]


def main():
    import chromadb
    from huggingface_hub import snapshot_download

    database = Path(os.environ["CHROMA_DB_PATH"])
    marker = database / ".docker-setup-complete"
    client = chromadb.PersistentClient(path=str(database))
    name = os.environ["COLLECTION_NAME"]
    collections = {item.name for item in client.list_collections()}
    fingerprint = hashlib.sha256(REVISION.encode())
    for source in os.environ["DATASETS_PATHS"].split(","):
        path = Path(source.strip())
        content = path.read_bytes()
        records = json.loads(content)
        if not isinstance(records, list) or not records:
            raise RuntimeError("Kaynak veri boş veya geçersiz.")
        fingerprint.update(path.name.encode())
        fingerprint.update(content)
    signature = fingerprint.hexdigest()
    if name in collections:
        count = client.get_collection(name).count()
        if not marker.exists() or marker.read_text().strip() != signature or not count:
            raise RuntimeError("Mevcut/yarım veya farklı kaynaklara ait indeks korunuyor. Temiz bir Docker volume ile hazırlayın.")
        print(f"İndeks hazır: {count} kayıt. Yeniden indeksleme yapılmadı.", flush=True)

    print("E5 önbelleği hazırlanıyor (ilk kurulum yaklaşık 1,13 GB). Gemma indirilmez.", flush=True)
    try:
        snapshot = snapshot_download(MODEL_ID, revision=REVISION, local_files_only=True)
        if not all((Path(snapshot) / file).is_file() for file in MODEL_FILES):
            raise FileNotFoundError("Eksik E5 dosyaları")
    except (OSError, ValueError):
        snapshot = snapshot_download(MODEL_ID, revision=REVISION, allow_patterns=MODEL_FILES)
    if Path(snapshot).resolve() != Path(os.environ["EMBEDDING_MODEL_NAME"]).resolve():
        raise RuntimeError("E5 model yolu yapılandırmayla eşleşmiyor.")

    if name not in collections:
        # The indexing process is offline and touches only the dedicated Docker volume.
        env = dict(os.environ, HF_HUB_OFFLINE="1")
        subprocess.run([sys.executable, "tck_indeksleme.py"], env=env, check=True)
        if client.get_collection(name).count() == 0:
            raise RuntimeError("İndeksleme tamamlandı fakat koleksiyon boş.")
        marker.write_text(signature + "\n", encoding="utf-8")
    print("Hazır. docker compose up -d komutunu çalıştırabilirsiniz.", flush=True)


if __name__ == "__main__":
    main()
