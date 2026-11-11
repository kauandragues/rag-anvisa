import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAKE_DIR = PROJECT_ROOT / "data_lake"
RAW_DIR = LAKE_DIR / "raw"
QUARANTINE_DIR = LAKE_DIR / "quarantine"
MANIFEST_PATH = LAKE_DIR / "manifest.json"
STATUS_VIGENCIA_VALIDOS = (
    "VIGENTE",
    "REVOGADA",
    "VIGENTE_COM_ALTERACAO",
    "ALTERADOR",
    "RETIFICADORA",
)


def calcular_sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def extrair_status_vigencia(nome_arquivo: str) -> str:
    """Lê o rótulo entre parênteses no início do nome do arquivo."""
    nome_normalizado = nome_arquivo.upper()
    for status in STATUS_VIGENCIA_VALIDOS:
        if nome_normalizado.startswith(f"({status})"):
            return status
    return "DESCONHECIDA"


def atualizar_manifesto(orgao: str) -> dict:
    """Cataloga arquivos e atualiza a vigência a partir dos rótulos nos nomes."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    manifesto = {}
    if MANIFEST_PATH.exists():
        manifesto = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for arquivo in RAW_DIR.iterdir():
        if not arquivo.is_file():
            continue

        # Regra de Quarentena: arquivos vazios ou menores que 100 bytes são movidos
        if arquivo.stat().st_size < 100:
            destino = QUARANTINE_DIR / arquivo.name
            shutil.move(str(arquivo), str(destino))
            print(f"[QUARENTENA] Arquivo inválido movido: {arquivo.name}")
            continue

        file_hash = calcular_sha256(arquivo)
        status_vigencia = extrair_status_vigencia(arquivo.name)
        if file_hash not in manifesto:
            manifesto[file_hash] = {
                "nome_arquivo": arquivo.name,
                "orgao": orgao,
                "tamanho_bytes": arquivo.stat().st_size,
                "status_vigencia": status_vigencia,
                "registrado_em": datetime.now().isoformat(),
            }
            print(f"[NOVO] Registrado no manifesto: {arquivo.name}")
        elif status_vigencia != "DESCONHECIDA":
            manifesto[file_hash].update(nome_arquivo=arquivo.name, status_vigencia=status_vigencia)

    MANIFEST_PATH.write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifesto


if __name__ == "__main__":
    catalogo = atualizar_manifesto(orgao="ANVISA")
    print(f"Total de documentos válidos no Data Lake: {len(catalogo)}")
