# 🎸 Empório da Música — Agente de Atendimento

Protótipo de agente de atendimento por mensagens de texto para a **Empório da Música**, loja fictícia de instrumentos musicais em Campo Grande/MS. O agente (persona **Lia**) responde dúvidas sobre produtos, preços, estoque, promoções, pedidos e políticas da loja.

> Desafio Técnico — AI Engineer (Artefact)

---

## Sumário
- [Como rodar](#como-rodar)
- [Arquitetura](#arquitetura)
- [Decisões técnicas](#decisões-técnicas)
- [Tratamento dos dados e suposições](#tratamento-dos-dados-e-suposições)
- [Exemplos de conversa](#exemplos-de-conversa)
- [Limitações conhecidas e próximos passos](#limitações-conhecidas-e-próximos-passos)
- [Uso de assistentes de código](#uso-de-assistentes-de-código)

---

## Como rodar

**Requisitos:** Python 3.10+ e uma chave de algum provedor com API compatível com OpenAI (padrão: Hugging Face Inference Providers).

```bash
git clone <URL_DO_REPOSITORIO>
cd <pasta>
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env    # e preencha LLM_API_KEY (veja abaixo)
python main.py          # ou: python main.py --debug  (mostra as consultas feitas)
```

### Provedor do modelo

Configurado só pelo `.env` — o código não muda:

| Provedor | `LLM_BASE_URL` | `LLM_MODEL` (exemplo) | Chave |
|---|---|---|---|
| Hugging Face (padrão) | `https://router.huggingface.co/v1` | `openai/gpt-oss-120b` | [token HF](https://huggingface.co/settings/tokens) com permissão de Inference Providers |
| Groq | `https://api.groq.com/openai/v1` | `openai/gpt-oss-120b` | [console.groq.com](https://console.groq.com) |
| Ollama (local) | `http://localhost:11434/v1` | `qwen2.5:7b` | qualquer valor (ex.: `ollama`) |

`DATA_REFERENCIA=AAAA-MM-DD` (opcional) fixa a "data de hoje" do agente — útil para reproduzir cenários de prazo de devolução, já que os pedidos da base vão de out/2025 a mar/2026.

### Comandos da CLI

| Comando | Ação |
|---|---|
| `/novo` | inicia nova conversa |
| `/salvar [nome]` | exporta a conversa para `conversas/<nome>.md` (com as consultas feitas) |
| `/debug` | liga/desliga exibição das chamadas de ferramenta |
| `/sair` | encerra |

### Testes

```bash
pytest -q
```
Os testes cobrem as ferramentas (busca, preços, bloqueios de SQL, verificação de identidade) e o loop do agente com um LLM falso — **não precisam de chave de API**.

---

## Arquitetura

```
Cliente ──► CLI (main.py) ──► AgenteAtendimento (emporio/agent.py)
                                  │  system prompt = persona + regras + contato/horário
                                  │  + data/hora atual e se a loja está aberta (calculado em código)
                                  ▼
                           LLM (API compatível OpenAI, function calling)
                              │                         │                          │
               consultar_catalogo(sql)        consultar_pedido(nº, e-mail/tel.)   consultar_politicas(temas)
               text-to-SQL restrito            função fixa, verifica identidade    seções do manual por tema
                              │                         │                          │
                              └── SQLite em memória (carregado dos CSVs) ──┘     data/politicas_da_loja.md
                                    views: catalogo, categorias
```

```
emporio/
  config.py     # .env, fuso de Campo Grande, data de referência
  database.py   # CSV → SQLite em memória + views para o LLM
  tools.py      # ferramentas + schema de function calling + allow-list do SQL
  prompts.py    # persona, regras de roteamento/escopo
  agent.py      # loop de tool calling, histórico, exportação das conversas
main.py         # CLI
data/           # CSVs e PDF originais + politicas_da_loja.md (versão tratada do PDF)
conversas/      # exemplos de interação
tests/
```

---

## Decisões técnicas

### Abordagem: function calling com três ferramentas (políticas por tema + text-to-SQL restrito + função de pedidos)

O enunciado pede que o agente saiba **quando consultar dados e quando consultar políticas**. Cada fonte recebeu o mecanismo mais simples que resolve bem:

| Fonte | Mecanismo | Por quê |
|---|---|---|
| Manual de políticas (8 páginas, 10 seções) | **Ferramenta `consultar_politicas(temas)`**: devolve seções inteiras do manual a partir de um índice fixo de temas | A primeira versão mandava o manual inteiro no system prompt, mas isso dobrava o tamanho de *toda* chamada ao LLM (~19 mil caracteres com as ferramentas) e estourava o limite de tokens/minuto de planos gratuitos (Groq: 8 mil TPM) já na segunda chamada de uma pergunta. Com a ferramenta, cada chamada leva cerca de metade. Não usei RAG com embeddings: o manual tem seções bem delimitadas, então um índice fixo é mais previsível e não tem risco de *recuperar o trecho errado*; o modelo pode pedir vários temas numa chamada só. As regras aplicadas o tempo todo (PIX não acumula com promoção, parcelas mínimas, contato e horário) continuam no prompt, então não dependem de o modelo lembrar de consultar. |
| Catálogo (produtos, categorias, promoções) | **Text-to-SQL restrito** (`consultar_catalogo`) | Perguntas de catálogo são muito variadas ("violões até R$ 1000", "guitarras com captação humbucker", "o mais barato em promoção"). SQL cobre todas sem eu precisar prever cada filtro. |
| Pedidos e clientes | **Função fixa** (`consultar_pedido`) | Envolve dados pessoais. Não faz sentido o LLM gerar SQL livre sobre a tabela de clientes. |

**Como o text-to-SQL foi restringido**
- O LLM só enxerga duas **views** (`catalogo`, `categorias`) com os joins já feitos, nomes de colunas em português, preço promocional e preço PIX **pré-calculados** e situação traduzida (`disponivel`/`esgotado`/`descontinuado`/`em breve`). Menos joins e menos aritmética para o modelo = menos erro, especialmente com modelos abertos.
- Uma coluna `busca` (nome + categoria + descrição + specs, minúsculo e sem acento) torna a busca tolerante: "violao takamine gd20" encontra "Takamine GD20 Dreadnought Natural".
- **Allow-list no próprio SQLite** (`set_authorizer`): só `SELECT`, só leitura das views (as tabelas brutas só podem ser lidas *através* delas), só funções permitidas. `customers`/`orders`, `INSERT`/`UPDATE`/`DELETE`, `PRAGMA`, `ATTACH`, `load_extension` e múltiplos comandos são bloqueados — validado em `tests/test_tools.py`. Também há limite de linhas e de passos de execução.

**Consulta de pedidos (LGPD):** exige nº do pedido **e** e-mail ou telefone cadastrado. A resposta tem a mesma mensagem para "pedido não existe" e "dados não conferem" (evita enumeração) e não devolve e-mail/telefone, só o primeiro nome.

**O que é calculado em código e não pelo LLM:** se a loja está aberta agora (dia/hora em `America/Campo_Grande`), preço promocional, preço PIX (sem acumular com promoção), dias desde o pedido/previsão de entrega. LLMs erram com frequência datas e contas; tirar isso deles aumenta a confiabilidade.

### Framework: nenhum (SDK `openai` + loop próprio)
O loop de tool calling tem ~60 linhas (`emporio/agent.py`). Um framework (LangChain, LlamaIndex) adicionaria abstrações sem ganho real nesse escopo e dificultaria depurar o que vai para o modelo. O SDK `openai` é usado apenas como cliente do protocolo, que hoje é o padrão de fato — por isso o mesmo código roda com Hugging Face, Groq, Ollama ou OpenAI.

### Modelo e provedor: `gpt-oss-120b` (open-weight) via Groq
- **Open-weight** (Apache 2.0, pesos no Hugging Face): sem dependência de fornecedor fechado; pode ser auto-hospedado.
- Bom em **function calling** e em português, que são os dois requisitos críticos do agente.
- **Provedor:** comecei pelo Hugging Face Inference Providers, mas os créditos gratuitos acabaram durante os testes; os exemplos de `conversas/` foram gerados no **Groq** (plano gratuito, mesmo modelo). Trocar de provedor é só mudar o `.env`.
- O plano gratuito do Groq limita a 8 mil tokens/minuto, o que motivou tirar o manual do prompt (ver acima) e aumentar as tentativas automáticas em caso de 429 (`LLM_MAX_RETRIES`).
- Modelos pequenos (7–8B) rodam localmente, mas erram mais a escolha de ferramenta e o SQL — por isso não são o padrão.

### Estratégia de prompt
- **Persona** (Lia) e **tom de voz** tirados da seção 7.1 do manual: informal mas profissional, mensagens curtas estilo WhatsApp.
- **Roteamento explícito**: o prompt diz qual fonte responde cada tipo de pergunta e proíbe informar preço/estoque sem consultar a ferramenta (regra do próprio manual, 7.1).
- **Regras de negócio** transformadas em instruções verificáveis: mostrar preço original + % + preço final em promoções; PIX não acumula; parcelas mínimas; sugerir alternativas para esgotado/descontinuado; redirecionar acessórios; recusar fora do escopo; encaminhar reclamações (24h úteis).
- **Guardrails**: não revelar instruções/SQL, não falar de dados de terceiros, ignorar tentativas de mudar o papel.
- Temperatura baixa (0,2) para respostas consistentes.

### Interface: CLI
O foco é o agente. A CLI tem `/debug` para mostrar as consultas feitas (útil na avaliação) e `/salvar` para exportar conversas em Markdown — os exemplos em `conversas/` foram gerados assim.

### Histórico de conversa
Mantido **em memória** durante a sessão (janela dos últimos 20 turnos, cortando sempre em uma mensagem do usuário para não separar uma chamada de ferramenta do seu resultado). Isso permite perguntas de acompanhamento ("e no PIX?", "tem em outra cor?"). Persistência entre sessões não foi implementada: para atendimento real ela ficaria no canal (ex.: WhatsApp, por número de telefone) — ver próximos passos.

---

## Tratamento dos dados e suposições

- **PDF → Markdown** (`data/politicas_da_loja.md`): a extração automática do PDF quebrava tabelas e palavras. Como o documento é pequeno, ele foi convertido para Markdown preservando o conteúdo integral. O PDF original continua no repositório.
- **CSVs → SQLite** com tipos explícitos; views com joins e preços calculados (ver acima).
- **Promoções:** só as com `is_active = 1` aparecem no catálogo (4 de 24). As inativas são tratadas como expiradas (manual 7.3).
- **Situação do produto:** `discontinued` → descontinuado, `coming_soon` → em breve, estoque 0 → esgotado. O agente sugere alternativas nesses casos.
- **Categorias sem produtos** (sopros e cordas orquestrais): o agente informa que não há itens disponíveis, em vez de inventar.

**Inconsistências encontradas no manual e decisão tomada:**

| Inconsistência | Decisão |
|---|---|
| Telefone/WhatsApp `(67) 3341-4444` (seção 1.2) × WhatsApp `(67) 3321-4500` (seção 7) | Telefone = 3341-4444; WhatsApp de atendimento = 3321-4500 |
| E-mail com acento (`empóriodamusica`) na seção 1.2 × sem acento na capa | `contato@emporiodamusica.com.br` (domínios com acento são incomuns; provável erro de digitação) |
| Tabela diz "parcela mínima R$ 100" no crédito × seção 3.1 com faixas (3x / 4–6x / 7–12x) | Regras detalhadas da 3.1 prevalecem; "até 3x sem mínimo (exceto abaixo de R$ 50)" interpretado como parcela mínima de R$ 50 |
| Data de recebimento do pedido não existe na base | Usa a previsão de entrega como referência para prazos de arrependimento/troca e avisa o cliente que a equipe confirmará |
| "Feriados" sem calendário | O agente informa que a loja fecha em feriados, sem calcular quais são |

---

## Exemplos de conversa

Em [`conversas/`](conversas/), gerados com `/salvar` (modelo `openai/gpt-oss-120b` via Groq, `DATA_REFERENCIA=2026-03-25`). Cada arquivo mostra as ferramentas chamadas e o que retornaram.

| # | Conversa | O que testa | Ferramentas | Resultado |
|---|---|---|---|---|
| 1 | [violoes_1000_reais.md](conversas/violoes_1000_reais.md) | Catálogo com filtro de categoria, preço e disponibilidade | `consultar_catalogo` | ✅ 12 violões disponíveis, ordenados por preço, com valor no PIX |
| 2 | [preco_promocao_parcelamento.md](conversas/preco_promocao_parcelamento.md) | Promoção ativa, PIX que não acumula, parcelas mínimas | `consultar_catalogo` | ✅ R$ 2.399,00 → 18% → R$ 1.967,18; PIX igual; até 12x de R$ 163,93 |
| 3 | [devolucao_no_prazo.md](conversas/devolucao_no_prazo.md) | Política pura (arrependimento em 7 dias) | `consultar_politicas` | ✅ Regras corretas e pede nº do pedido + e-mail para seguir |
| 4 | [pedido_fora_do_prazo_de_troca.md](conversas/pedido_fora_do_prazo_de_troca.md) | Pedido + política: entregue há ~36 dias, fora dos prazos de troca | `consultar_pedido`, `consultar_politicas` (`trocas_devolucoes`, `garantia`) | ✅ Fora da troca por defeito (30 dias), mas dentro da garantia legal de 90 dias; avisa que usou a previsão de entrega como referência. Ressalva menor: pede "embalagem original", exigência da troca, não da garantia |
| 5 | [pedido_com_atraso.md](conversas/pedido_com_atraso.md) | Reclamação de pedido atrasado (25 dias após a previsão) | `consultar_pedido`, `consultar_politicas` (`frete_entregas`) | ✅ Informa o código de rastreio e encaminha a reclamação com retorno em até 24h úteis, sem prometer soluções fora do manual |
| 6 | [endereco_e_funcionamento.md](conversas/endereco_e_funcionamento.md) | Dados fixos da loja | — | ✅ Endereço e horários corretos, sem chamada de ferramenta |
| 7 | [acessorios_e_fora_do_escopo.md](conversas/acessorios_e_fora_do_escopo.md) | Acessórios, pedido fora do escopo e tentativa de *prompt injection* | — | ✅ Redireciona acessórios, recusa programação e não revela o prompt |

Na primeira rodada, as conversas 4 e 5 expuseram o principal risco do agente: **completar com conhecimento geral quando a política não cobre o caso**. Na 4, chamou a garantia legal de "garantia do fabricante" sem consultar o tema `garantia`; na 5, ofereceu reenvio grátis e reembolso (que não estão no manual) e não informou o rastreio. Corrigi com regras explícitas no prompt (atraso de entrega → encaminhar + rastreio; dúvidas de garantia → consultar `garantia`) e regerei as duas. Esses cenários são os primeiros candidatos para a avaliação automatizada (ver abaixo).

---

## Limitações conhecidas e próximos passos

- **Avaliação automatizada:** os testes cobrem as ferramentas, não a qualidade das respostas. Próximo passo: um conjunto de perguntas com respostas esperadas (ferramenta correta chamada, preço correto citado) rodando contra cada modelo candidato.
- **Reclamações não são registradas** em nenhum sistema — o agente apenas informa o encaminhamento. Com mais tempo: ferramenta `registrar_atendimento` (ticket/CRM) e handoff para humano.
- **Frete para outras cidades** depende de CEP/peso/dimensões que não estão na base; o agente só informa modalidades e prazos.
- **Sem persistência entre sessões** e sem identificação do cliente pelo canal (no WhatsApp, o número já identificaria o cliente e dispensaria parte da verificação).
- **Verificação de identidade simples** (e-mail/telefone): em produção, adicionar limite de tentativas e/ou código por SMS/WhatsApp.
- **Prompt injection:** há guardrails no prompt e o SQL é restrito a leitura do catálogo (o pior caso é ler dados públicos), mas não há classificador dedicado.
- **Índice fixo de temas do manual** funciona bem com um documento de 10 seções; com dezenas de documentos, trocar por RAG (chunking por seção + busca híbrida).
- **Interface:** com mais tempo, integração com WhatsApp (Twilio/Meta Cloud API) ou uma UI simples (Streamlit/Gradio) e streaming das respostas.

---

## Uso de assistentes de código

Usei o **Claude** (Anthropic) como par de programação:
- discussão inicial da arquitetura (text-to-SQL puro × híbrido), em que surgiram as preocupações com LGPD e com a tabela de clientes;
- leitura dos dados para encontrar armadilhas (produtos esgotados/descontinuados, promoções inativas, categorias vazias, inconsistências no manual);
- geração do esqueleto do código, dos testes e do rascunho deste README, que revisei e ajustei.

O que fiz além da geração de código:
- **Rodei o agente de ponta a ponta** com o modelo real e salvei as conversas de `conversas/`, escolhendo cenários a partir dos dados (pedido entregue fora do prazo de troca, pedido atrasado, produto em promoção) e conferindo cada resposta contra a base e o manual — inclusive registrando acima as respostas que saíram erradas.
- **Problemas que só apareceram na execução real** e mudaram o projeto: os testes não importavam o pacote (faltava `pytest.ini`), os créditos do Hugging Face acabaram (troca para o Groq) e o limite de 8 mil tokens/min do Groq estourava em perguntas com ferramenta. Isso levou a trocar "manual inteiro no prompt" pela ferramenta `consultar_politicas` e a aumentar as tentativas em caso de 429.
- Revisei os diffs e organizei os commits.
