-- 1. Ativa a extensão de vetores (pgvector) no PostgreSQL
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Tabela principal para registrar cada documento baixado (PDF, HTML, Excel)
CREATE TABLE IF NOT EXISTS documentos_regulatorios (
    id SERIAL PRIMARY KEY,
    orgao VARCHAR(10) NOT NULL,           -- Ex: 'ANS', 'CVM' ou 'ANVISA'
    tipo_norma VARCHAR(50) NOT NULL,      -- Ex: 'RN', 'Resolucao', 'RDC'
    numero_norma VARCHAR(50) NOT NULL,    -- Ex: '465/2021'
    status_vigencia VARCHAR(20) DEFAULT 'VIGENTE', -- 'VIGENTE' ou 'REVOGADA'
    hash_sha256 VARCHAR(64) UNIQUE NOT NULL,       -- Impede arquivos duplicados
    caminho_arquivo TEXT NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabela que guardará os pedaços de texto (chunks) e seus vetores nas próximas etapas
CREATE TABLE IF NOT EXISTS chunks_regulatorios (
    id SERIAL PRIMARY KEY,
    documento_id INT REFERENCES documentos_regulatorios(id) ON DELETE CASCADE,
    hierarquia_normativa TEXT,            -- Ex: 'Art. 5º > Parágrafo 1º'
    texto_chunk TEXT NOT NULL,
    embedding vector(1024)                -- Vetor de 1024 dimensões (modelo BGE-M3)
);
