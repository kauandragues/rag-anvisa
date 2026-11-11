import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime

import pytest

from src import datalake_manager


@pytest.fixture
def lake_temporario(tmp_path, monkeypatch):
    lake_dir = tmp_path / "data_lake"
    monkeypatch.setattr(datalake_manager, "LAKE_DIR", lake_dir)
    monkeypatch.setattr(datalake_manager, "RAW_DIR", lake_dir / "raw")
    monkeypatch.setattr(datalake_manager, "QUARANTINE_DIR", lake_dir / "quarantine")
    monkeypatch.setattr(datalake_manager, "MANIFEST_PATH", lake_dir / "manifest.json")
    datalake_manager.RAW_DIR.mkdir(parents=True)
    return lake_dir


def test_calcular_sha256(tmp_path):
    arquivo = tmp_path / "documento.txt"
    arquivo.write_bytes(b"abc")

    assert datalake_manager.calcular_sha256(arquivo) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


@pytest.mark.parametrize("pasta_execucao", ["projeto", "projeto/src", "externo"])
def test_execucao_usa_data_lake_do_projeto(tmp_path, pasta_execucao):
    projeto = tmp_path / "projeto"
    script = projeto / "src" / "datalake_manager.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(datalake_manager.__file__, script)
    diretorio_execucao = tmp_path / pasta_execucao
    diretorio_execucao.mkdir(parents=True, exist_ok=True)

    resultado = subprocess.run(
        [sys.executable, "-X", "utf8", str(script)],
        cwd=diretorio_execucao,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr
    lake_dir = projeto / "data_lake"
    assert (lake_dir / "raw").is_dir()
    assert (lake_dir / "quarantine").is_dir()
    assert json.loads((lake_dir / "manifest.json").read_text(encoding="utf-8")) == {}
    if diretorio_execucao != projeto:
        assert not (diretorio_execucao / "data_lake").exists()


def test_catalogacao_quarentena_e_deduplicacao(lake_temporario):
    raw_dir = lake_temporario / "raw"
    conteudo = b"documento regulatorio\n" * 8
    (raw_dir / "norma.pdf").write_bytes(conteudo)
    (raw_dir / "copia.pdf").write_bytes(conteudo)
    (raw_dir / "vazio.pdf").write_bytes(b"")
    (raw_dir / "pequeno.pdf").write_bytes(b"x" * 99)
    (raw_dir / "limite.pdf").write_bytes(b"x" * 100)
    (raw_dir / "subpasta").mkdir()
    (raw_dir / "subpasta" / "ignorado.pdf").write_bytes(b"")

    manifesto = datalake_manager.atualizar_manifesto(orgao="ANVISA")

    assert len(manifesto) == 2
    registro = manifesto[hashlib.sha256(conteudo).hexdigest()]
    assert registro["nome_arquivo"] in {"norma.pdf", "copia.pdf"}
    assert registro["orgao"] == "ANVISA"
    assert registro["tamanho_bytes"] == len(conteudo)
    assert registro["status_vigencia"] == "DESCONHECIDA"
    datetime.fromisoformat(registro["registrado_em"])
    assert {arquivo.name for arquivo in (lake_temporario / "quarantine").iterdir()} == {
        "vazio.pdf",
        "pequeno.pdf",
    }
    assert {arquivo.name for arquivo in raw_dir.iterdir()} == {
        "norma.pdf",
        "copia.pdf",
        "limite.pdf",
        "subpasta",
    }
    assert (raw_dir / "subpasta" / "ignorado.pdf").is_file()
    assert json.loads(datalake_manager.MANIFEST_PATH.read_text(encoding="utf-8")) == manifesto
    assert datalake_manager.atualizar_manifesto(orgao="ANVISA") == manifesto


def test_preserva_metadados_de_documento_ja_catalogado(lake_temporario):
    conteudo = b"norma com vigencia verificada\n" * 8
    (lake_temporario / "raw" / "norma.pdf").write_bytes(conteudo)
    manifesto_existente = {
        hashlib.sha256(conteudo).hexdigest(): {
            "nome_arquivo": "norma.pdf",
            "orgao": "ANVISA",
            "tamanho_bytes": len(conteudo),
            "status_vigencia": "REVOGADA",
            "registrado_em": "2026-11-10T12:00:00",
        }
    }
    datalake_manager.MANIFEST_PATH.write_text(json.dumps(manifesto_existente), encoding="utf-8")

    assert datalake_manager.atualizar_manifesto(orgao="ANVISA") == manifesto_existente
    assert json.loads(datalake_manager.MANIFEST_PATH.read_text(encoding="utf-8")) == (
        manifesto_existente
    )


@pytest.mark.parametrize(
    ("nome_arquivo", "status_esperado"),
    [
        ("(Vigente)norma.pdf", "VIGENTE"),
        ("(Revogada)norma.pdf", "REVOGADA"),
        ("(Vigente_com_alteracao)norma.pdf", "VIGENTE_COM_ALTERACAO"),
        ("(Alterador)norma.pdf", "ALTERADOR"),
        ("(Retificadora)norma.pdf", "RETIFICADORA"),
        ("(vIgEnTe)norma.pdf", "VIGENTE"),
        ("(Vigente)(Vigente)norma.pdf", "VIGENTE"),
        ("(Outro)norma.pdf", "DESCONHECIDA"),
    ],
)
def test_catalogacao_obtem_vigencia_do_nome(lake_temporario, nome_arquivo, status_esperado):
    conteudo = b"documento com rotulo de vigencia\n" * 8
    (lake_temporario / "raw" / nome_arquivo).write_bytes(conteudo)

    manifesto = datalake_manager.atualizar_manifesto(orgao="ANVISA")

    registro = manifesto[hashlib.sha256(conteudo).hexdigest()]
    assert registro["nome_arquivo"] == nome_arquivo
    assert registro["status_vigencia"] == status_esperado
    assert json.loads(datalake_manager.MANIFEST_PATH.read_text(encoding="utf-8")) == manifesto


def test_atualiza_vigencia_de_documento_renomeado(lake_temporario):
    arquivo = lake_temporario / "raw" / "norma.pdf"
    conteudo = b"documento ja catalogado\n" * 8
    arquivo.write_bytes(conteudo)
    file_hash = hashlib.sha256(conteudo).hexdigest()
    manifesto_inicial = datalake_manager.atualizar_manifesto(orgao="ANVISA")
    registro_inicial = manifesto_inicial[file_hash]

    for rotulo, status_esperado in [("Vigente", "VIGENTE"), ("Revogada", "REVOGADA")]:
        arquivo = arquivo.rename(arquivo.with_name(f"({rotulo})norma.pdf"))

        manifesto = datalake_manager.atualizar_manifesto(orgao="ANVISA")

        assert len(manifesto) == 1
        assert manifesto[file_hash] == {
            **registro_inicial,
            "nome_arquivo": arquivo.name,
            "status_vigencia": status_esperado,
        }
        assert json.loads(datalake_manager.MANIFEST_PATH.read_text(encoding="utf-8")) == manifesto
