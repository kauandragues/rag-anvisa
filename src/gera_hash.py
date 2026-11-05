import hashlib
from pathlib import Path

pasta_raw = Path("../data_lake/raw")

for arquivo in pasta_raw.iterdir():
    if arquivo.is_file():
        hash_sha256 = hashlib.sha256(arquivo.read_bytes()).hexdigest()
        print(f"Arquivo: {arquivo.name} | SHA-256: {hash_sha256}")
