# Violoes 1000 reais

_Modelo: `openai/gpt-oss-120b`_

**Cliente:** Quais são as opções de violão por até R$1.000,00?

<details><summary>Consultas feitas pelo agente</summary>

`consultar_catalogo`
```json
{
  "sql": "SELECT nome, preco_tabela, desconto_percentual, preco_promocional, preco_pix, situacao FROM catalogo WHERE categoria = 'Violões' AND situacao = 'disponivel' AND COALESCE(preco_promocional, preco_tabela) <= 1000 ORDER BY COALESCE(preco_promocional, preco_tabela) LIMIT 25"
}
```
Resultado:
```json
{"colunas": ["nome", "preco_tabela", "desconto_percentual", "preco_promocional", "preco_pix", "situacao"], "linhas": [["Tagima Memphis AC-39 Nylon Natural", 429.9, null, null, 408.4, "disponivel"], ["Rozini RC-104 Nylon Estudante", 459.9, null, null, 436.9, "disponivel"], ["Shelby SN-100 Folk Aço Preto", 549.0, null, null, 521.55, "disponivel"], ["Giannini GF-1R Aço Folk Sunburst", 579.9, null, null, 550.9, "disponivel"], ["Yamaha C40 Nylon Natural", 599.9, null, null, 569.9, "disponivel"], ["Giannini GN-15 Nylon Cedr Natural", 689.0, null, null, 654.55, "disponivel"], ["Yamaha F310 Aço Natural", 699.9, null, null, 664.9, "disponivel"], ["Tagima Dallas Tuner Aço Natural", 749.0, null, null, 711.55, "disponivel"], ["Shelby SGD-195E Elétrico Aço Sunburst", 799.0, null, null, 759.05, "disponivel"], ["Yamaha C70 Nylon Natural", 849.0, null, null, 806.55, "disponivel"], ["Tagima Woodstock Dreadnought Natural", 899.0, null, null, 854.05, "disponivel"], ["Tagima TW-7 7 Cordas Aço Natural", 999.0, null, null, 949.05, "disponivel"]], "total_linhas": 12, "truncado": false}
```

</details>

**Lia:** Oi! Seguem os violões disponíveis por até **R$ 1.000,00** (preço de tabela) e o valor com desconto no PIX (5 % off):

- **Tagima Memphis AC‑39 Nylon Natural** – R$ 429,90 (PIX: R$ 408,40)  
- **Rozini RC‑104 Nylon Estudante** – R$ 459,90 (PIX: R$ 436,90)  
- **Shelby SN‑100 Folk Aço Preto** – R$ 549,00 (PIX: R$ 521,55)  
- **Giannini GF‑1R Aço Folk Sunburst** – R$ 579,90 (PIX: R$ 550,90)  
- **Yamaha C40 Nylon Natural** – R$ 599,90 (PIX: R$ 569,90)  
- **Giannini GN‑15 Nylon Cedr Natural** – R$ 689,00 (PIX: R$ 654,55)  
- **Yamaha F310 Aço Natural** – R$ 699,90 (PIX: R$ 664,90)  
- **Tagima Dallas Tuner Aço Natural** – R$ 749,00 (PIX: R$ 711,55)  
- **Shelby SGD‑195E Elétrico Aço Sunburst** – R$ 799,00 (PIX: R$ 759,05)  
- **Yamaha C70 Nylon Natural** – R$ 849,00 (PIX: R$ 806,55)  
- **Tagima Woodstock Dreadnought Natural** – R$ 899,00 (PIX: R$ 854,05)  
- **Tagima TW‑7 7 Cordas Aço Natural** – R$ 999,00 (PIX: R$ 949,05)

Todos estão em estoque e prontos para envio. Posso ajudar a simular o parcelamento ou a reservar algum modelo? 🎸

---
