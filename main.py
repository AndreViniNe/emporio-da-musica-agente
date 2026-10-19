"""CLI do agente de atendimento da Empório da Música.

Uso:
    python main.py            # conversa interativa
    python main.py --debug    # mostra as ferramentas chamadas a cada resposta

Comandos durante a conversa:
    /novo            inicia uma nova conversa (limpa o histórico)
    /salvar [nome]   salva a conversa em conversas/<nome>.md
    /debug           liga/desliga a exibição das ferramentas
    /sair            encerra
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime

from emporio.agent import AgenteAtendimento
from emporio.config import CONVERSAS_DIR, get_settings

CINZA, VERDE, RESET = "\033[90m", "\033[92m", "\033[0m"


def salvar(agente: AgenteAtendimento, nome: str | None) -> None:
    if not agente.turnos:
        print("(nada para salvar ainda)")
        return
    nome = re.sub(r"[^\w\-]+", "_", nome or f"conversa_{datetime.now():%Y%m%d_%H%M%S}")
    CONVERSAS_DIR.mkdir(exist_ok=True)
    caminho = CONVERSAS_DIR / f"{nome}.md"
    caminho.write_text(agente.exportar_markdown(titulo=nome.replace("_", " ").capitalize()), encoding="utf-8")
    print(f"(conversa salva em {caminho.relative_to(CONVERSAS_DIR.parent)})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Agente de atendimento — Empório da Música")
    parser.add_argument("--debug", action="store_true", help="mostra as chamadas de ferramenta")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.api_key:
        print("⚠️  LLM_API_KEY não definida. Copie .env.example para .env e preencha (veja o README).")
        return 1

    agente = AgenteAtendimento(settings)
    debug = args.debug
    print(f"🎸 Empório da Música — assistente virtual (modelo: {settings.model})")
    print("Digite sua mensagem. Comandos: /novo, /salvar [nome], /debug, /sair\n")

    while True:
        try:
            mensagem = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not mensagem:
            continue
        if mensagem.startswith("/"):
            comando, _, resto = mensagem.partition(" ")
            if comando == "/sair":
                break
            if comando == "/novo":
                agente.nova_conversa()
                print("(nova conversa iniciada)\n")
            elif comando == "/salvar":
                salvar(agente, resto.strip() or None)
            elif comando == "/debug":
                debug = not debug
                print(f"(debug {'ligado' if debug else 'desligado'})")
            else:
                print("Comando desconhecido.")
            continue

        try:
            turno = agente.responder(mensagem)
        except RuntimeError as exc:
            print(f"❌ {exc}\n")
            continue

        if debug:
            for f in turno.ferramentas:
                print(f"{CINZA}  ↳ {f.nome}({f.argumentos})\n    → {f.resultado[:400]}{RESET}")
        print(f"{VERDE}Lia:{RESET} {turno.resposta}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
