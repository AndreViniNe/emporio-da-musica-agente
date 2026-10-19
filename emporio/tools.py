"""Ferramentas (function calling) disponíveis para o agente.

- consultar_catalogo: text-to-SQL restrito (somente SELECT nas views `catalogo` e `categorias`).
- consultar_pedido: função fixa com verificação de identidade (nº do pedido + e-mail/telefone).
- consultar_politicas: devolve seções inteiras do manual por tema (sem embeddings: o manual tem
  10 seções bem delimitadas, então um índice fixo é mais previsível que busca semântica).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from functools import cache
from typing import Any, Callable

from .config import POLITICAS_PATH
from .database import normalizar

MAX_LINHAS = 25
MAX_PASSOS_SQL = 200_000  # aborta consultas patológicas (ex.: CTE recursiva infinita)

VIEWS_PERMITIDAS = {"catalogo", "categorias"}
FUNCOES_PERMITIDAS = {
    "normalizar", "lower", "upper", "round", "abs", "min", "max", "avg", "sum", "count",
    "total", "coalesce", "ifnull", "nullif", "length", "substr", "substring", "instr",
    "replace", "trim", "ltrim", "rtrim", "like", "glob", "json_extract", "printf", "format",
    "group_concat", "random", "iif", "cast",
}

STATUS_PEDIDO = {
    "pending": ("pendente", "Pedido recebido, aguardando confirmação do pagamento."),
    "confirmed": ("confirmado", "Pagamento confirmado; pedido em separação, ainda não despachado."),
    "shipped": ("enviado", "Pedido despachado e a caminho."),
    "delivered": ("entregue", "Pedido entregue."),
    "cancelled": ("cancelado", "Pedido cancelado."),
}

FORMAS_PAGAMENTO = {"pix": "PIX", "debit": "Cartão de débito", "boleto": "Boleto bancário"}


# --------------------------------------------------------------------------- #
# consultar_catalogo
# --------------------------------------------------------------------------- #
def _autorizador(acao: int, arg1: str | None, arg2: str | None, _db: str | None, origem: str | None) -> int:
    """Allow-list do SQLite: só leitura das views permitidas (e das tabelas *através* delas)."""
    if acao == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if acao == sqlite3.SQLITE_READ:
        # arg1 = tabela lida; origem = view responsável pelo acesso (None se for SQL direto)
        if arg1 in VIEWS_PERMITIDAS or origem in VIEWS_PERMITIDAS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    if acao == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK if (arg2 or "").lower() in FUNCOES_PERMITIDAS else sqlite3.SQLITE_DENY
    if acao == sqlite3.SQLITE_RECURSIVE:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY  # INSERT/UPDATE/DELETE/PRAGMA/ATTACH/CREATE...


def consultar_catalogo(conn: sqlite3.Connection, sql: str) -> dict[str, Any]:
    sql = (sql or "").strip().rstrip(";")
    if not re.match(r"(?is)^\s*(select|with)\b", sql):
        return {"erro": "Apenas consultas SELECT são permitidas."}
    if ";" in sql:
        return {"erro": "Envie apenas uma consulta por vez."}

    passos = 0

    def _limite() -> int:
        nonlocal passos
        passos += 1
        return 1 if passos > MAX_PASSOS_SQL // 1000 else 0

    conn.set_authorizer(_autorizador)
    conn.set_progress_handler(_limite, 1000)
    try:
        cursor = conn.execute(sql)
        colunas = [d[0] for d in cursor.description]
        linhas = cursor.fetchmany(MAX_LINHAS + 1)
    except sqlite3.DatabaseError as exc:
        return {
            "erro": f"Erro na consulta: {exc}. Use apenas as views `catalogo` e `categorias`.",
        }
    finally:
        conn.set_authorizer(None)
        conn.set_progress_handler(None, 0)

    truncado = len(linhas) > MAX_LINHAS
    linhas = linhas[:MAX_LINHAS]
    return {
        "colunas": colunas,
        "linhas": [list(row) for row in linhas],
        "total_linhas": len(linhas),
        "truncado": truncado,
    }


# --------------------------------------------------------------------------- #
# consultar_pedido
# --------------------------------------------------------------------------- #
def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def _identidade_confere(informado: str, email: str, telefone: str) -> bool:
    informado = (informado or "").strip()
    if not informado:
        return False
    if "@" in informado:
        return normalizar(informado) == normalizar(email)
    digitos_inf, digitos_cad = _so_digitos(informado), _so_digitos(telefone)
    # Aceita com ou sem DDD/código do país: compara os últimos 8 dígitos (mínimo 8).
    return len(digitos_inf) >= 8 and digitos_cad.endswith(digitos_inf[-8:])


def _forma_pagamento(codigo: str) -> str:
    if codigo in FORMAS_PAGAMENTO:
        return FORMAS_PAGAMENTO[codigo]
    m = re.match(r"credit_(\d+)x", codigo or "")
    if m:
        return f"Cartão de crédito em {m.group(1)}x"
    return codigo


def consultar_pedido(
    conn: sqlite3.Connection, numero_pedido: int, email_ou_telefone: str, hoje: date
) -> dict[str, Any]:
    nao_encontrado = {
        "erro": "Não encontrei um pedido com esse número e esse e-mail/telefone. "
        "Peça para o cliente conferir os dados."
    }
    try:
        numero_pedido = int(numero_pedido)
    except (TypeError, ValueError):
        return nao_encontrado

    pedido = conn.execute(
        """SELECT o.*, c.name AS cliente, c.email, c.phone
             FROM orders o JOIN customers c ON c.customer_id = o.customer_id
            WHERE o.order_id = ?""",
        (numero_pedido,),
    ).fetchone()
    # Mesma mensagem para "não existe" e "dados não conferem": evita enumerar pedidos.
    if pedido is None or not _identidade_confere(email_ou_telefone, pedido["email"], pedido["phone"]):
        return nao_encontrado

    itens = conn.execute(
        """SELECT p.name AS produto, i.quantity AS quantidade
             FROM order_items i JOIN products p ON p.product_id = i.product_id
            WHERE i.order_id = ?""",
        (numero_pedido,),
    ).fetchall()

    status, descricao = STATUS_PEDIDO.get(pedido["status"], (pedido["status"], ""))
    data_pedido = date.fromisoformat(pedido["order_date"])
    previsao = pedido["estimated_delivery"]

    resultado: dict[str, Any] = {
        "numero_pedido": pedido["order_id"],
        "primeiro_nome_cliente": pedido["cliente"].split()[0],
        "data_pedido": pedido["order_date"],
        "dias_desde_o_pedido": (hoje - data_pedido).days,
        "status": status,
        "descricao_status": descricao,
        "valor_total": pedido["total_brl"],
        "forma_pagamento": _forma_pagamento(pedido["payment_method"]),
        "itens": [dict(i) for i in itens],
        "codigo_rastreio": pedido["tracking_code"],
        "previsao_entrega": previsao,
        "observacoes": pedido["notes"],
        "data_de_hoje": hoje.isoformat(),
    }
    if previsao:
        resultado["dias_desde_a_previsao_de_entrega"] = (hoje - date.fromisoformat(previsao)).days
    if pedido["status"] == "delivered":
        resultado["aviso"] = (
            "A base não registra a data exata de recebimento; use a previsão de entrega como "
            "referência e deixe isso claro ao cliente ao calcular prazos de troca/devolução."
        )
    return resultado


# --------------------------------------------------------------------------- #
# consultar_politicas
# --------------------------------------------------------------------------- #
# tema -> (nº da seção "## N." no manual, o que ela cobre). A descrição vai para o schema da tool.
TEMAS_POLITICA: dict[str, tuple[int, str]] = {
    "empresa": (1, "sobre a loja, missão, dados cadastrais (CNPJ, razão social), o que a loja vende"),
    "horario": (2, "horário de funcionamento, feriados, datas especiais"),
    "pagamento": (3, "formas de pagamento, desconto PIX, parcelamento, combinar formas de pagamento"),
    "trocas_devolucoes": (4, "arrependimento (7 dias), troca por defeito, troca por preferência, itens não elegíveis, reembolso"),
    "frete_entregas": (5, "frete em Campo Grande e outras cidades, prazos, transportadoras, seguro, avaria, rastreio"),
    "promocoes": (6, "campanhas do ano (Black Friday etc.), cumulatividade, rain check"),
    "atendimento": (7, "diretrizes do WhatsApp, fluxo de atendimento, produto esgotado/descontinuado, reclamações"),
    "garantia": (8, "garantia legal (90 dias), garantia do fabricante, o que não é coberto"),
    "privacidade": (9, "LGPD, uso e exclusão de dados pessoais"),
    "disposicoes_finais": (10, "uso do manual, quando consultar a gerência"),
}


@cache
def _secoes_manual() -> dict[int, str]:
    """Divide o manual nos blocos de nível "## N. Título" (cada um inclui suas subseções)."""
    secoes: dict[int, str] = {}
    atual: int | None = None
    for linha in POLITICAS_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (\d+)\.", linha)
        if m:
            atual = int(m.group(1))
            secoes[atual] = ""
        if atual is not None:
            secoes[atual] += linha + "\n"
    return {n: texto.strip() for n, texto in secoes.items()}


def consultar_politicas(temas: list[str]) -> dict[str, Any]:
    if isinstance(temas, str):
        temas = [temas]
    validos = [t for t in dict.fromkeys(temas or []) if t in TEMAS_POLITICA]
    if not validos:
        return {"erro": f"Tema inválido. Use um ou mais de: {', '.join(TEMAS_POLITICA)}."}
    secoes = _secoes_manual()
    return {"secoes": [{"tema": t, "texto": secoes[TEMAS_POLITICA[t][0]]} for t in validos]}


# --------------------------------------------------------------------------- #
# Definições para o LLM (formato OpenAI tools)
# --------------------------------------------------------------------------- #
DESCRICAO_CATALOGO = """Executa UMA consulta SQL (SQLite, somente SELECT) no catálogo da loja.
Use para QUALQUER informação de produto: preço, estoque, disponibilidade, promoções, especificações, opções por categoria/faixa de preço.

Views disponíveis (nenhuma outra tabela é acessível):

catalogo(
  produto_id INTEGER,
  nome TEXT,                 -- ex.: 'Takamine GD20 Dreadnought Natural'
  categoria TEXT,            -- 'Guitarras','Baixos','Baterias e Percussão','Teclados e Pianos','Violões','Instrumentos de Sopro (Madeiras)','Instrumentos de Sopro (Metais)','Cordas Orquestrais','Ukuleles'
  descricao TEXT,
  preco_tabela REAL,         -- preço original em R$
  promocao TEXT,             -- nome da promoção ATIVA (NULL se não houver)
  desconto_percentual REAL,  -- NULL se não houver promoção ativa
  preco_promocional REAL,    -- NULL se não houver promoção ativa
  preco_pix REAL,            -- preço no PIX (5% off; não acumula com promoção)
  estoque INTEGER,
  situacao TEXT,             -- 'disponivel' | 'esgotado' | 'descontinuado' | 'em breve'
  especificacoes TEXT,       -- JSON, ex.: json_extract(especificacoes,'$.strings') = 'nylon'
  busca TEXT                 -- nome+categoria+descrição+specs em minúsculas e SEM acento
)
categorias(categoria TEXT, descricao TEXT, produtos_disponiveis INTEGER)

Regras:
- Para buscar por nome/termo use `busca LIKE '%termo%'` com o termo em minúsculas e sem acento (ex.: '%violao%', '%takamine%gd20%').
- Para "preço até X" compare com COALESCE(preco_promocional, preco_tabela).
- Ao listar opções para compra, filtre situacao = 'disponivel', a menos que o cliente pergunte por um produto específico.
- Máximo de 25 linhas por resultado; use ORDER BY e LIMIT.

Exemplo: SELECT nome, preco_tabela, desconto_percentual, preco_promocional, situacao FROM catalogo WHERE categoria = 'Violões' AND situacao = 'disponivel' AND COALESCE(preco_promocional, preco_tabela) <= 1000 ORDER BY COALESCE(preco_promocional, preco_tabela) LIMIT 10"""

DESCRICAO_PEDIDO = """Consulta status, itens, rastreio e previsão de entrega de um pedido.
Exige o número do pedido E o e-mail ou telefone cadastrado do cliente (verificação de identidade).
Se o cliente não informou os dois, peça antes de chamar."""

DESCRICAO_POLITICAS = """Retorna o texto oficial de seções do Manual de Políticas da loja.
Use ANTES de responder qualquer dúvida sobre regras da loja (trocas, devoluções, frete, garantia, pagamento, parcelamento, promoções, privacidade etc.). Peça todos os temas necessários numa única chamada.

Temas:
""" + "\n".join(f"- {tema}: {desc}" for tema, (_, desc) in TEMAS_POLITICA.items())

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "consultar_catalogo",
            "description": DESCRICAO_CATALOGO,
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string", "description": "Consulta SELECT em SQLite."}},
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_pedido",
            "description": DESCRICAO_PEDIDO,
            "parameters": {
                "type": "object",
                "properties": {
                    "numero_pedido": {"type": "integer", "description": "Número do pedido."},
                    "email_ou_telefone": {
                        "type": "string",
                        "description": "E-mail ou telefone cadastrado, como o cliente informou.",
                    },
                },
                "required": ["numero_pedido", "email_ou_telefone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_politicas",
            "description": DESCRICAO_POLITICAS,
            "parameters": {
                "type": "object",
                "properties": {
                    "temas": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(TEMAS_POLITICA)},
                        "description": "Um ou mais temas do manual.",
                    },
                },
                "required": ["temas"],
            },
        },
    },
]


def criar_executor(conn: sqlite3.Connection, hoje: Callable[[], date]) -> Callable[[str, str], str]:
    """Retorna uma função (nome_tool, argumentos_json) -> resultado em JSON (string)."""

    def executar(nome: str, argumentos: str) -> str:
        try:
            args = json.loads(argumentos or "{}")
        except json.JSONDecodeError:
            return json.dumps({"erro": "Argumentos inválidos (JSON malformado)."}, ensure_ascii=False)
        try:
            if nome == "consultar_catalogo":
                resultado = consultar_catalogo(conn, args.get("sql", ""))
            elif nome == "consultar_pedido":
                resultado = consultar_pedido(
                    conn, args.get("numero_pedido"), args.get("email_ou_telefone", ""), hoje()
                )
            elif nome == "consultar_politicas":
                resultado = consultar_politicas(args.get("temas", []))
            else:
                resultado = {"erro": f"Ferramenta desconhecida: {nome}"}
        except Exception as exc:  # nunca derrubar a conversa por erro de ferramenta
            resultado = {"erro": f"Falha ao executar {nome}: {exc}"}
        return json.dumps(resultado, ensure_ascii=False, default=str)

    return executar
