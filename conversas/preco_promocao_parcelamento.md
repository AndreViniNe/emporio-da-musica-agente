# Preco promocao parcelamento

_Modelo: `openai/gpt-oss-120b`_

**Cliente:** Quanto custa o violão Crafter HT-100? Se eu pagar no PIX fica mais barato? E em quantas vezes consigo parcelar?

<details><summary>Consultas feitas pelo agente</summary>

`consultar_catalogo`
```json
{
  "sql": "SELECT nome, preco_tabela, desconto_percentual, preco_promocional, preco_pix, situacao FROM catalogo WHERE busca LIKE '%crafter%ht-100%'"
}
```
Resultado:
```json
{"colunas": ["nome", "preco_tabela", "desconto_percentual", "preco_promocional", "preco_pix", "situacao"], "linhas": [["Crafter HT-100 Folk Aço Natural", 2399.0, 18.0, 1967.18, 1967.18, "disponivel"]], "total_linhas": 1, "truncado": false}
```

</details>

**Lia:** Oi! O violão **Crafter HT‑100 Folk Aço Natural** está disponível e tem:

- **Preço de tabela:** R$ 2.399,00  
- **Promoção ativa:** 18 % de desconto → **R$ 1.967,18**  
- **PIX:** o mesmo valor da promoção (R$ 1.967,18), pois o desconto do PIX não se acumula com a promoção.

**Parcelamento (sem juros)**  
Como o valor final é R$ 1.967,18, você pode dividir em até **12 vezes** (mínimo de R$ 100 por parcela). Algumas opções:

- 3x de R$ 655,73  
- 6x de R$ 327,86  
- 12x de R$ 163,93  

Posso ajudar em mais alguma coisa?

---
