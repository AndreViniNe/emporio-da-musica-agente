"""Carrega os CSVs da loja em um SQLite em memória e expõe views pensadas para o LLM.

Decisões:
- SQLite em memória: base pequena (~200 linhas), zero infraestrutura, SQL padrão.
- O LLM NÃO enxerga as tabelas brutas. Ele consulta apenas as views `catalogo` e
  `categorias`, que já trazem os joins (produto + categoria + promoção ativa), preços
  calculados e situação traduzida. Isso reduz erros de SQL e impede acesso a dados
  de clientes (LGPD).
- Pedidos são acessados apenas pela função `consultar_pedido` (tools.py), que exige
  verificação de identidade.
"""
from __future__ import annotations

import csv
import sqlite3
import unicodedata
from pathlib import Path

from .config import DATA_DIR

PREFIXO_CSV = "desafio_tecnico_ai_eng - "

# Tabela -> colunas com tipos (os CSVs não trazem tipos).
SCHEMA: dict[str, dict[str, str]] = {
    "categories": {"category_id": "INTEGER PRIMARY KEY", "name": "TEXT", "description": "TEXT"},
    "products": {
        "product_id": "INTEGER PRIMARY KEY",
        "price_brl": "REAL",
        "name": "TEXT",
        "category_id": "INTEGER",
        "description": "TEXT",
        "stock_quantity": "INTEGER",
        "status": "TEXT",
        "specs": "TEXT",
        "created_at": "TEXT",
    },
    "promotions": {
        "promotion_id": "INTEGER PRIMARY KEY",
        "product_id": "INTEGER",
        "discount_percent": "REAL",
        "description": "TEXT",
        "is_active": "INTEGER",
    },
    "customers": {
        "customer_id": "INTEGER PRIMARY KEY",
        "name": "TEXT",
        "phone": "TEXT",
        "email": "TEXT",
        "city": "TEXT",
    },
    "orders": {
        "order_id": "INTEGER PRIMARY KEY",
        "customer_id": "INTEGER",
        "order_date": "TEXT",
        "status": "TEXT",
        "total_brl": "REAL",
        "payment_method": "TEXT",
        "tracking_code": "TEXT",
        "estimated_delivery": "TEXT",
        "notes": "TEXT",
    },
    "order_items": {"order_id": "INTEGER", "quantity": "INTEGER", "product_id": "INTEGER"},
}

VIEWS_SQL = """
CREATE VIEW catalogo AS
SELECT
    p.product_id                                   AS produto_id,
    p.name                                         AS nome,
    c.name                                         AS categoria,
    p.description                                  AS descricao,
    p.price_brl                                    AS preco_tabela,
    pr.description                                 AS promocao,
    pr.discount_percent                            AS desconto_percentual,
    CASE WHEN pr.promotion_id IS NOT NULL
         THEN ROUND(p.price_brl * (1 - pr.discount_percent / 100.0), 2) END
                                                   AS preco_promocional,
    -- PIX dá 5% de desconto, mas não acumula com promoção (política 6.2)
    CASE WHEN pr.promotion_id IS NOT NULL
         THEN ROUND(p.price_brl * (1 - pr.discount_percent / 100.0), 2)
         ELSE ROUND(p.price_brl * 0.95, 2) END     AS preco_pix,
    p.stock_quantity                               AS estoque,
    CASE
        WHEN p.status = 'discontinued' THEN 'descontinuado'
        WHEN p.status = 'coming_soon'  THEN 'em breve'
        WHEN p.stock_quantity <= 0     THEN 'esgotado'
        ELSE 'disponivel'
    END                                            AS situacao,
    p.specs                                        AS especificacoes,
    normalizar(p.name || ' ' || c.name || ' ' || p.description || ' ' || COALESCE(p.specs, ''))
                                                   AS busca
FROM products p
JOIN categories c ON c.category_id = p.category_id
LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active = 1;

CREATE VIEW categorias AS
SELECT
    c.name        AS categoria,
    c.description AS descricao,
    (SELECT COUNT(*) FROM products p
      WHERE p.category_id = c.category_id
        AND p.status = 'active' AND p.stock_quantity > 0) AS produtos_disponiveis
FROM categories c;
"""


def normalizar(texto: str | None) -> str:
    """Minúsculas e sem acentos, para buscas tolerantes ('Violão' == 'violao')."""
    if texto is None:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    return "".join(ch for ch in sem_acento if not unicodedata.combining(ch)).lower()


def _converter(valor: str, tipo: str):
    valor = valor.strip()
    if valor == "":
        return None
    if tipo.startswith("INTEGER"):
        return int(float(valor))
    if tipo == "REAL":
        return float(valor)
    return valor


def _caminho_csv(tabela: str, data_dir: Path) -> Path:
    caminho = data_dir / f"{PREFIXO_CSV}{tabela}.csv"
    if not caminho.exists():
        raise FileNotFoundError(f"CSV não encontrado: {caminho}")
    return caminho


def criar_conexao(data_dir: Path = DATA_DIR) -> sqlite3.Connection:
    """Cria o banco em memória a partir dos CSVs e retorna a conexão."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.create_function("normalizar", 1, normalizar, deterministic=True)

    for tabela, colunas in SCHEMA.items():
        defs = ", ".join(f"{col} {tipo}" for col, tipo in colunas.items())
        conn.execute(f"CREATE TABLE {tabela} ({defs})")
        with open(_caminho_csv(tabela, data_dir), encoding="utf-8", newline="") as f:
            linhas = [
                tuple(_converter(row.get(col, "") or "", tipo) for col, tipo in colunas.items())
                for row in csv.DictReader(f)
            ]
        marcadores = ", ".join("?" for _ in colunas)
        conn.executemany(f"INSERT INTO {tabela} VALUES ({marcadores})", linhas)

    conn.executescript(VIEWS_SQL)
    conn.commit()
    return conn
