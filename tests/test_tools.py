"""Testes das ferramentas (não precisam de LLM nem de chave de API)."""
from datetime import date

import pytest

from emporio.database import criar_conexao
from emporio.tools import consultar_catalogo, consultar_pedido

HOJE = date(2026, 3, 25)


@pytest.fixture(scope="module")
def conn():
    return criar_conexao()


# ---------------------------- catálogo ---------------------------- #
def test_busca_por_nome_sem_acento(conn):
    r = consultar_catalogo(conn, "SELECT nome, preco_tabela FROM catalogo WHERE busca LIKE '%takamine%gd20%'")
    assert r["linhas"] == [["Takamine GD20 Dreadnought Natural", 2199.0]]


def test_violoes_ate_1000(conn):
    r = consultar_catalogo(
        conn,
        "SELECT nome FROM catalogo WHERE categoria='Violões' AND situacao='disponivel' "
        "AND COALESCE(preco_promocional, preco_tabela) <= 1000",
    )
    assert r["total_linhas"] > 0
    assert "Giannini GF-3D Dreadnought Sunburst" not in [l[0] for l in r["linhas"]]  # esgotado


def test_promocao_ativa_e_pix_nao_acumula(conn):
    r = consultar_catalogo(
        conn,
        "SELECT preco_tabela, desconto_percentual, preco_promocional, preco_pix "
        "FROM catalogo WHERE busca LIKE '%taylor 110e%'",
    )
    tabela, desconto, promo, pix = r["linhas"][0]
    assert desconto == 8 and promo == pytest.approx(tabela * 0.92, abs=0.01) and pix == promo


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM customers",
        "SELECT * FROM orders",
        "SELECT email FROM catalogo JOIN customers",
        "DELETE FROM products",
        "UPDATE products SET price_brl = 1",
        "SELECT 1; DROP TABLE products",
        "PRAGMA table_info(customers)",
        "SELECT load_extension('x')",
        "WITH x AS (SELECT * FROM customers) SELECT * FROM x",
    ],
)
def test_sql_bloqueado(conn, sql):
    assert "erro" in consultar_catalogo(conn, sql)


def test_tabela_intacta_apos_tentativas(conn):
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 65


# ---------------------------- pedidos ---------------------------- #
def test_pedido_com_email_correto(conn):
    r = consultar_pedido(conn, 8, "AnaCarol.Ferreira@coldmail.com", HOJE)
    assert r["status"] == "enviado" and r["codigo_rastreio"] == "BRJL5544332BR"
    assert "email" not in r and "phone" not in r  # não vaza dados pessoais


def test_pedido_com_telefone_sem_formatacao(conn):
    r = consultar_pedido(conn, 8, "67996547821", HOJE)
    assert r["numero_pedido"] == 8


def test_pedido_com_identidade_errada(conn):
    assert "erro" in consultar_pedido(conn, 8, "lucas.mendes@jmail.com", HOJE)


def test_pedido_inexistente_mesma_mensagem(conn):
    assert consultar_pedido(conn, 999, "x@x.com", HOJE) == consultar_pedido(conn, 8, "x@x.com", HOJE)


def test_consulta_infinita_e_abortada(conn):
    r = consultar_catalogo(conn, "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM n) SELECT count(*) FROM n")
    assert "erro" in r
