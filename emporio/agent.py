"""Loop do agente: chat completions + function calling (API compatível com OpenAI).

Sem framework (LangChain etc.) de propósito: o loop é pequeno, fácil de ler/depurar e
funciona igual com Hugging Face, Groq, Ollama ou OpenAI, trocando só o .env.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI, OpenAIError

from .config import Settings, agora_loja
from .database import criar_conexao
from .prompts import montar_system_prompt
from .tools import TOOLS_SCHEMA, criar_executor

MAX_RODADAS_FERRAMENTA = 6   # evita loops infinitos de tool calling
MAX_TURNOS_HISTORICO = 20    # janela de memória (turnos do usuário)


@dataclass
class ChamadaFerramenta:
    nome: str
    argumentos: str
    resultado: str


@dataclass
class Turno:
    usuario: str
    resposta: str
    ferramentas: list[ChamadaFerramenta] = field(default_factory=list)


class AgenteAtendimento:
    def __init__(self, settings: Settings, client: OpenAI | None = None):
        self.settings = settings
        self.client = client or OpenAI(base_url=settings.base_url, api_key=settings.api_key or "sem-chave")
        self.conn = criar_conexao()
        self.executar_ferramenta = criar_executor(
            self.conn, hoje=lambda: agora_loja(settings.data_referencia).date()
        )
        self.historico: list[dict[str, Any]] = []  # mensagens user/assistant/tool (sem o system)
        self.turnos: list[Turno] = []              # registro legível para exportar conversas

    # ------------------------------------------------------------------ #
    def nova_conversa(self) -> None:
        self.historico.clear()
        self.turnos.clear()

    def _mensagens(self) -> list[dict[str, Any]]:
        system = {"role": "system", "content": montar_system_prompt(agora_loja(self.settings.data_referencia))}
        return [system, *self.historico]

    def _aparar_historico(self) -> None:
        """Mantém só os últimos N turnos, cortando sempre no início de uma mensagem do usuário
        (para nunca separar um tool_call do seu resultado)."""
        inicios = [i for i, m in enumerate(self.historico) if m["role"] == "user"]
        if len(inicios) > MAX_TURNOS_HISTORICO:
            self.historico = self.historico[inicios[-MAX_TURNOS_HISTORICO]:]

    # ------------------------------------------------------------------ #
    def responder(self, mensagem: str) -> Turno:
        self.historico.append({"role": "user", "content": mensagem})
        self._aparar_historico()
        turno = Turno(usuario=mensagem, resposta="")

        try:
            for _ in range(MAX_RODADAS_FERRAMENTA + 1):
                resposta = self.client.chat.completions.create(
                    model=self.settings.model,
                    messages=self._mensagens(),
                    tools=TOOLS_SCHEMA,
                    tool_choice="auto",
                    temperature=self.settings.temperature,
                )
                msg = resposta.choices[0].message
                tool_calls = msg.tool_calls or []

                if not tool_calls:
                    turno.resposta = (msg.content or "").strip()
                    self.historico.append({"role": "assistant", "content": turno.resposta})
                    break

                self.historico.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in tool_calls
                    ],
                })
                for tc in tool_calls:
                    resultado = self.executar_ferramenta(tc.function.name, tc.function.arguments)
                    turno.ferramentas.append(ChamadaFerramenta(tc.function.name, tc.function.arguments, resultado))
                    self.historico.append({"role": "tool", "tool_call_id": tc.id, "content": resultado})
            else:
                turno.resposta = ("Desculpa, me enrolei aqui para buscar essa informação. 😅 "
                                  "Pode reformular a pergunta ou falar com a equipe no WhatsApp (67) 3321-4500?")
                self.historico.append({"role": "assistant", "content": turno.resposta})
        except OpenAIError as exc:
            # Remove a mensagem do usuário que ficou sem resposta para não corromper o histórico.
            while self.historico and self.historico[-1]["role"] != "user":
                self.historico.pop()
            if self.historico:
                self.historico.pop()
            raise RuntimeError(f"Erro ao chamar o modelo ({self.settings.model}): {exc}") from exc

        self.turnos.append(turno)
        return turno

    # ------------------------------------------------------------------ #
    def exportar_markdown(self, titulo: str = "Conversa", incluir_ferramentas: bool = True) -> str:
        linhas = [f"# {titulo}", "", f"_Modelo: `{self.settings.model}`_", ""]
        for t in self.turnos:
            linhas += [f"**Cliente:** {t.usuario}", ""]
            if incluir_ferramentas and t.ferramentas:
                linhas.append("<details><summary>Consultas feitas pelo agente</summary>\n")
                for f in t.ferramentas:
                    try:
                        args = json.dumps(json.loads(f.argumentos), ensure_ascii=False, indent=2)
                    except json.JSONDecodeError:
                        args = f.argumentos
                    linhas += [f"`{f.nome}`", "```json", args, "```",
                               "Resultado:", "```json", f.resultado[:1500], "```", ""]
                linhas.append("</details>\n")
            linhas += [f"**Lia:** {t.resposta}", "", "---", ""]
        return "\n".join(linhas)
