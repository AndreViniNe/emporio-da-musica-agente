"""Testa o loop do agente com um cliente LLM falso (sem rede/chave)."""
import json
from types import SimpleNamespace as NS

from emporio.agent import AgenteAtendimento
from emporio.config import Settings
from emporio.prompts import montar_system_prompt
from emporio.config import agora_loja


def _resposta(content=None, tool_calls=None):
    return NS(choices=[NS(message=NS(content=content, tool_calls=tool_calls))])


def _tool_call(id_, nome, args):
    return NS(id=id_, function=NS(name=nome, arguments=json.dumps(args)))


class ClienteFalso:
    """1ª chamada: pede consultar_catalogo; 2ª: responde em texto usando o resultado."""

    def __init__(self):
        self.chamadas = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        if len(self.chamadas) == 1:
            sql = "SELECT nome, preco_tabela FROM catalogo WHERE busca LIKE '%takamine%gd20%'"
            return _resposta(tool_calls=[_tool_call("c1", "consultar_catalogo", {"sql": sql})])
        resultado = json.loads(kwargs["messages"][-1]["content"])
        nome, preco = resultado["linhas"][0]
        return _resposta(content=f"O {nome} sai por R$ {preco:.2f}.")


def test_loop_com_ferramenta():
    settings = Settings("http://x", "k", "fake", 0.0, None)
    cliente = ClienteFalso()
    agente = AgenteAtendimento(settings, client=cliente)

    turno = agente.responder("Quanto custa o Takamine GD20?")

    assert "2199.00" in turno.resposta
    assert [f.nome for f in turno.ferramentas] == ["consultar_catalogo"]
    assert [m["role"] for m in agente.historico] == ["user", "assistant", "tool", "assistant"]
    assert cliente.chamadas[0]["messages"][0]["role"] == "system"
    assert "Consultas feitas pelo agente" in agente.exportar_markdown()


def test_system_prompt_roteia_politicas_para_ferramenta():
    prompt = montar_system_prompt(agora_loja())
    assert "A loja está" in prompt and "consultar_politicas" in prompt
    assert "Direito de Arrependimento" not in prompt  # o manual não vai mais inteiro no prompt
