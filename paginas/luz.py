"""Página da luz: ler a fatura e comparar com outras ofertas."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from contas.energia import POTENCIAS_PADRAO, DadosFatura, comparar, custo_periodo, ler_fatura_pdf
from contas.recorrentes import euro
from ui.componentes import Linha, cabecalho, discreto, talao
from ui.dados import ofertas_base

cabecalho("A tua luz está cara?",
          "Carrega a fatura da luz em PDF ou escreve os valores à mão. O BillWatch calcula quanto pagarias "
          "com outras ofertas, para o mesmo consumo.")

_base = ofertas_base()
if "fonte" in _base and _base["fonte"].astype(str).str.contains("EXEMPLO", case=False).any():
    st.warning("**Demonstração.** As ofertas desta página são de comercializadoras fictícias, com preços "
               "inventados: servem para mostrar como funciona a comparação. A leitura da fatura e as contas são "
               "reais. Para comparar com preços atuais, carrega uma tabela de ofertas em *Usar a minha tabela de "
               "ofertas*, ou usa o simulador da ERSE.", icon=":material/science:")

for chave, padrao in {"consumo": None, "dias": 30, "potencia": 4.6, "preco_kwh": None, "termo_fixo": None}.items():
    st.session_state.setdefault(chave, padrao)

pdf = st.file_uploader("Fatura da luz", type=["pdf"], help="O PDF que a comercializadora te envia.")
# Preencher os campos uma única vez por ficheiro (para não apagar correções do utilizador).
if pdf is not None and st.session_state.get("pdf_lido") != pdf.file_id:
    try:
        dados, texto = ler_fatura_pdf(pdf.getvalue())
    except Exception:  # noqa: BLE001  PDF protegido, digitalizado ou danificado
        dados, texto = DadosFatura(), ""
    st.session_state["pdf_lido"] = pdf.file_id
    st.session_state["texto_pdf"] = texto
    if dados.consumo_kwh:
        st.session_state["consumo"] = float(dados.consumo_kwh)
    if dados.dias:
        st.session_state["dias"] = int(dados.dias)
    if dados.potencia_kva in POTENCIAS_PADRAO:
        st.session_state["potencia"] = dados.potencia_kva
    if dados.preco_kwh:
        st.session_state["preco_kwh"] = float(dados.preco_kwh)
    if dados.termo_fixo_dia:
        st.session_state["termo_fixo"] = float(dados.termo_fixo_dia)
    encontrados = dados.campos_encontrados()
    st.session_state["pdf_msg"] = (f"Li {len(encontrados)} de 6 valores da fatura. Confirma-os em baixo."
                                   if encontrados else
                                   "Não consegui ler valores desta fatura. Escreve-os à mão em baixo.")
if pdf is not None and "pdf_msg" in st.session_state:
    st.info(st.session_state["pdf_msg"])

st.subheader("Os valores da tua fatura", anchor=False)
c1, c2 = st.columns(2)
consumo = c1.number_input("Consumo no período (kWh)", 0.0, 10000.0, key="consumo", placeholder="ex.: 185",
                          step=1.0)
dias = c2.number_input("Dias do período", 1, 90, key="dias")
potencia = c1.selectbox("Potência contratada (kVA)", POTENCIAS_PADRAO, key="potencia")
preco_kwh = c2.number_input("Preço da energia (€/kWh)", 0.0, 1.0, key="preco_kwh", placeholder="ex.: 0,1580",
                            step=0.001, format="%.4f")
termo_fixo = c1.number_input("Termo fixo (€/dia)", 0.0, 3.0, key="termo_fixo", placeholder="ex.: 0,2650",
                             step=0.001, format="%.4f")

with st.expander("Usar a minha tabela de ofertas"):
    discreto("CSV com as colunas comercializadora, tarifario, potencia_kva, termo_fixo_eur_dia e preco_kwh.")
    proprio = st.file_uploader("Tabela de ofertas", type=["csv"], key="ofertas_csv")
ofertas = pd.read_csv(proprio) if proprio is not None else ofertas_base()

if not consumo:
    discreto("Escreve pelo menos o consumo para ver a comparação.")
else:
    custo_atual = custo_periodo(consumo, dias, termo_fixo, preco_kwh) if preco_kwh and termo_fixo else None
    resultado = comparar(consumo, potencia, ofertas, custo_atual=custo_atual, dias=dias)
    st.divider()
    st.subheader("A comparação", anchor=False)
    if resultado.empty:
        st.warning(f"A tabela de ofertas não tem nenhuma oferta para {potencia:g} kVA.".replace(".", ",", 1))
    else:
        melhor = resultado.iloc[0]
        nome_melhor = f"{melhor['comercializadora']}, {melhor['tarifario']}"
        linhas = []
        if custo_atual is not None:
            linhas.append(Linha("A tua fatura", euro(custo_atual * 30.4 / dias) + "/mês"))
        linhas.append(Linha(nome_melhor, euro(melhor["custo_mensal"]) + "/mês",
                            nota="a oferta mais barata para o teu consumo"))
        blocos = [(None, linhas)]
        if custo_atual is not None:
            poupanca = float(melhor["poupanca_anual"])
            blocos += [("---", []), (None, [Linha("Poupavas por ano", euro(max(poupanca, 0)), "total",
                                                   "" if poupanca > 0 else "já tens uma das ofertas mais baratas")])]
        fonte = ("Ofertas da tua tabela" if proprio is not None else
                 "Ofertas de exemplo, não são preços reais")
        kva = f"{potencia:g}".replace(".", ",")
        talao(["BillWatch", "Fatura da luz", f"{consumo:g} kWh em {dias} dias, {kva} kVA", fonte], blocos,
              "Valores antes de IVA e taxas, que são quase iguais em todas as comercializadoras.")
        if custo_atual is None:
            discreto("Escreve o preço da energia e o termo fixo da tua fatura para saber quanto poupavas.")

        with st.expander(f"Ver as {len(resultado)} ofertas para {kva} kVA"):
            colunas = ["comercializadora", "tarifario", "custo_mensal", "custo_anual", "fidelizacao"]
            if "poupanca_anual" in resultado:
                colunas.insert(4, "poupanca_anual")
            st.dataframe(resultado[[c for c in colunas if c in resultado]], hide_index=True, width="stretch",
                         column_config={
                             "comercializadora": "Comercializadora", "tarifario": "Tarifário",
                             "custo_mensal": st.column_config.NumberColumn("Por mês", format="%.2f €"),
                             "custo_anual": st.column_config.NumberColumn("Por ano", format="%.2f €"),
                             "poupanca_anual": st.column_config.NumberColumn("Poupança por ano", format="%.2f €"),
                             "fidelizacao": "Fidelização"})
        if pdf is not None and st.session_state.get("texto_pdf"):
            with st.expander("Ver o texto lido da fatura"):
                st.text(st.session_state["texto_pdf"][:3000])
