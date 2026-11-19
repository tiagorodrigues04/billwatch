"""BillWatch — descobre quanto pagas todos os meses e onde podes poupar.

Correr localmente:  streamlit run app.py
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from contas.energia import POTENCIAS_PADRAO, carregar_ofertas, comparar, custo_periodo, ler_fatura_pdf
from contas.exemplo import extrato_csv_banco, gerar_extrato
from contas.extrato import carregar_extrato
from contas.recorrentes import Parametros, detetar_recorrentes, euro, preparar, resumo

AZUL = "#2a78d6"

st.set_page_config(page_title="BillWatch", page_icon="👀", layout="centered")
st.title("👀 BillWatch")
st.caption("Descobre quanto pagas todos os meses — e onde estás a pagar a mais.")

aba_subs, aba_luz, aba_sobre = st.tabs(["💳 Subscrições", "⚡ Luz", "ℹ️ Como funciona"])


# ---------------------------------------------------------------------------
# Funções com cache (não recalcular a cada clique)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _csv_exemplo() -> bytes:
    return extrato_csv_banco(gerar_extrato())


@st.cache_data(show_spinner=False)
def _ler_extrato(conteudo: bytes) -> pd.DataFrame:
    return carregar_extrato(conteudo)


@st.cache_data(show_spinner=False)
def _ofertas_base() -> pd.DataFrame:
    return carregar_ofertas()


# ---------------------------------------------------------------------------
# Aba 1 — Subscrições
# ---------------------------------------------------------------------------

def pagina_subscricoes() -> None:
    st.subheader("Que pagamentos se repetem na tua conta?")
    st.write(
        "Exporta o extrato da tua conta em **CSV** (na app ou no site do banco, normalmente em "
        "*Movimentos → Exportar*) com pelo menos 3 meses. Quanto mais meses, melhor."
    )
    ficheiro = st.file_uploader("Extrato bancário (.csv)", type=["csv", "txt"])
    col_a, col_b = st.columns(2)
    usar_exemplo = ficheiro is None and col_a.toggle("Usar dados de exemplo", value=True)
    col_b.download_button("Descarregar extrato de exemplo", _csv_exemplo(), "extrato_exemplo.csv", "text/csv")
    st.caption("🔒 O ficheiro é processado só em memória e não é guardado.")

    conteudo = ficheiro.getvalue() if ficheiro is not None else (_csv_exemplo() if usar_exemplo else None)
    if conteudo is None:
        return
    try:
        extrato = _ler_extrato(conteudo)
    except ValueError as erro:
        st.error(str(erro))
        return

    with st.expander("Afinar a deteção"):
        p = Parametros(
            min_pagamentos=st.slider("Mínimo de pagamentos (comerciantes desconhecidos)", 2, 6, 3),
            regularidade_minima=st.slider("Regularidade mínima dos intervalos", 0.5, 1.0, 0.7, 0.05),
            variacao_maxima_valor=st.slider("Variação máxima do valor", 0.05, 0.5, 0.15, 0.05),
        )

    recorrentes = detetar_recorrentes(extrato, p)
    periodo = f"{extrato['data'].min():%d/%m/%Y} a {extrato['data'].max():%d/%m/%Y}"
    st.caption(f"{len(extrato)} movimentos lidos, de {periodo}.")

    if recorrentes.empty:
        st.info("Não encontrei pagamentos recorrentes. Experimenta um extrato com mais meses.")
        return

    # O utilizador pode dizer "isto não é uma subscrição" (o algoritmo erra às vezes).
    excluir = st.multiselect(
        "Algum destes não é um pagamento fixo? Retira-o das contas:",
        options=recorrentes["comerciante"].tolist(),
        placeholder="Escolhe um ou mais serviços",
    )
    recorrentes = recorrentes[~recorrentes["comerciante"].isin(excluir)]
    r = resumo(recorrentes)

    c1, c2, c3 = st.columns(3)
    c1.metric("Pagas por mês", euro(r["mensal"]))
    c2.metric("Por ano", euro(r["anual"]))
    c3.metric("Pagamentos fixos ativos", r["n_ativas"])

    alertas = [(linha.comerciante, a) for linha in recorrentes.itertuples() for a in linha.alertas]
    if alertas:
        st.markdown("#### ⚠️ Alertas")
        for comerciante, alerta in alertas:
            st.warning(f"**{comerciante}** — {alerta}")

    st.markdown("#### Os teus pagamentos fixos")
    tabela = recorrentes.assign(
        confianca=(recorrentes["confianca"] * 100).round(),
        estado=recorrentes["ativa"].map({True: "Ativa", False: "Parada"}),
        valor=[f"{euro(v)}{' (média)' if var else ''}" for v, var in
               zip(recorrentes["valor_tipico"], recorrentes["valor_variavel"])],
    )
    st.dataframe(
        tabela[["comerciante", "categoria", "periodicidade", "valor", "custo_anual",
                "proximo_previsto", "estado", "confianca"]],
        hide_index=True,
        width="stretch",
        column_config={
            "comerciante": "Serviço",
            "categoria": "Categoria",
            "periodicidade": "Frequência",
            "valor": "Valor",
            "custo_anual": st.column_config.NumberColumn("Por ano", format="%.2f €"),
            "proximo_previsto": st.column_config.DateColumn("Próximo", format="DD/MM/YYYY"),
            "estado": "Estado",
            "confianca": st.column_config.ProgressColumn("Confiança", min_value=0, max_value=100, format="%d%%"),
        },
    )

    ativas = recorrentes[recorrentes["ativa"]]
    if not ativas.empty:
        st.markdown("#### Onde vai o dinheiro (por mês)")
        por_categoria = ativas.groupby("categoria", as_index=False)["custo_mensal"].sum()
        grafico = (
            alt.Chart(por_categoria)
            .mark_bar(color=AZUL, cornerRadiusEnd=4, size=18)
            .encode(
                x=alt.X("custo_mensal:Q", title="€ por mês", axis=alt.Axis(grid=False)),
                y=alt.Y("categoria:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("categoria:N", title="Categoria"),
                         alt.Tooltip("custo_mensal:Q", title="€ por mês", format=".2f")],
            )
            .properties(height=40 * len(por_categoria) + 20)
        )
        st.altair_chart(grafico, width="stretch")

    with st.expander("Ver os movimentos de um serviço"):
        escolhido = st.selectbox("Serviço", recorrentes["comerciante"].tolist())
        movimentos = preparar(extrato)
        st.dataframe(
            movimentos[movimentos["comerciante"] == escolhido][["data", "descricao", "montante"]],
            hide_index=True, width="stretch",
            column_config={"data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                           "descricao": "Descrição",
                           "montante": st.column_config.NumberColumn("Valor", format="%.2f €")},
        )

with aba_subs:
    pagina_subscricoes()

# ---------------------------------------------------------------------------
# Aba 2 — Luz
# ---------------------------------------------------------------------------

with aba_luz:
    st.subheader("Estás a pagar a luz mais cara do que devias?")
    st.write("Carrega a fatura em PDF para preencher os campos automaticamente, ou escreve-os à mão.")

    for chave, padrao in {"consumo": None, "dias": 30, "potencia": 4.6, "preco_kwh": None, "termo_fixo": None}.items():
        st.session_state.setdefault(chave, padrao)

    pdf = st.file_uploader("Fatura da luz (.pdf)", type=["pdf"])
    # Preencher os campos uma única vez por ficheiro (para não apagar correções do utilizador).
    if pdf is not None and st.session_state.get("pdf_lido") != pdf.file_id:
        dados, texto = ler_fatura_pdf(pdf.getvalue())
        st.session_state["pdf_lido"] = pdf.file_id
        st.session_state["texto_pdf"] = texto
        if dados.consumo_kwh: st.session_state["consumo"] = float(dados.consumo_kwh)  # noqa: E701
        if dados.dias: st.session_state["dias"] = int(dados.dias)  # noqa: E701
        if dados.potencia_kva in POTENCIAS_PADRAO: st.session_state["potencia"] = dados.potencia_kva  # noqa: E701
        if dados.preco_kwh: st.session_state["preco_kwh"] = float(dados.preco_kwh)  # noqa: E701
        if dados.termo_fixo_dia: st.session_state["termo_fixo"] = float(dados.termo_fixo_dia)  # noqa: E701
        encontrados = dados.campos_encontrados()
        st.session_state["pdf_msg"] = (
            f"Li {len(encontrados)} de 6 campos da fatura. Confirma os valores abaixo."
            if encontrados else "Não consegui ler esta fatura. Preenche os campos à mão."
        )
    if pdf is not None and "pdf_msg" in st.session_state:
        st.info(st.session_state["pdf_msg"])
        with st.expander("Texto lido do PDF"):
            st.text(st.session_state.get("texto_pdf", "")[:3000])

    c1, c2 = st.columns(2)
    consumo = c1.number_input("Consumo no período (kWh)", 0.0, 10000.0, key="consumo",
                              placeholder="ex.: 185", step=1.0)
    dias = c2.number_input("Dias do período", 1, 90, key="dias")
    potencia = c1.selectbox("Potência contratada (kVA)", POTENCIAS_PADRAO, key="potencia")
    preco_kwh = c2.number_input("Preço atual da energia (€/kWh)", 0.0, 1.0, key="preco_kwh",
                                placeholder="ex.: 0,1580", step=0.001, format="%.4f")
    termo_fixo = c1.number_input("Termo fixo atual (€/dia)", 0.0, 3.0, key="termo_fixo",
                                 placeholder="ex.: 0,2650", step=0.001, format="%.4f")

    with st.expander("Usar a minha própria tabela de ofertas"):
        st.caption("CSV com as colunas: comercializadora, tarifario, potencia_kva, termo_fixo_eur_dia, preco_kwh")
        proprio = st.file_uploader("Tabela de ofertas (.csv)", type=["csv"], key="ofertas_csv")
    ofertas = pd.read_csv(proprio) if proprio is not None else _ofertas_base()
    if proprio is None:
        st.caption("⚠️ As ofertas incluídas são **valores de exemplo**, não preços reais. "
                   "Antes de publicar, substitui `dados/ofertas_luz.csv` por dados atuais.")

    if consumo:
        custo_atual = (custo_periodo(consumo, dias, termo_fixo, preco_kwh)
                       if preco_kwh and termo_fixo else None)
        resultado = comparar(consumo, potencia, ofertas, custo_atual=custo_atual, dias=dias)
        if resultado.empty:
            st.warning(f"Não há ofertas na tabela para {potencia} kVA.")
        else:
            melhor = resultado.iloc[0]
            m1, m2 = st.columns(2)
            if custo_atual is not None:
                m1.metric("Pagas hoje (por mês, s/ impostos)", euro(custo_atual * 30.4 / dias))
                poupanca = melhor["poupanca_anual"]
                if poupanca > 0:
                    m2.metric("Poupavas por ano", euro(poupanca))
                    st.success(f"A oferta mais barata é **{melhor['comercializadora']} — {melhor['tarifario']}**.")
                else:
                    m2.metric("Poupavas por ano", euro(0))
                    st.success("Já tens um dos tarifários mais baratos da tabela. 👏")
            else:
                st.info("Indica o preço atual da energia e o termo fixo para calcular quanto poupavas.")

            colunas = ["comercializadora", "tarifario", "custo_mensal", "custo_anual", "fidelizacao"]
            if "poupanca_anual" in resultado:
                colunas.insert(4, "poupanca_anual")
            st.dataframe(
                resultado[[c for c in colunas if c in resultado]],
                hide_index=True, width="stretch",
                column_config={
                    "comercializadora": "Comercializadora",
                    "tarifario": "Tarifário",
                    "custo_mensal": st.column_config.NumberColumn("Por mês", format="%.2f €"),
                    "custo_anual": st.column_config.NumberColumn("Por ano", format="%.2f €"),
                    "poupanca_anual": st.column_config.NumberColumn("Poupança/ano", format="%.2f €"),
                    "fidelizacao": "Fidelização",
                },
            )
            st.caption("Custos antes de IVA e taxas, que são praticamente iguais em todas as "
                       "comercializadoras e por isso não mudam qual é a mais barata.")

# ---------------------------------------------------------------------------
# Aba 3 — Como funciona
# ---------------------------------------------------------------------------

with aba_sobre:
    st.markdown(
        """
**Subscrições.** A app procura pagamentos ao mesmo comerciante que se repetem com um
intervalo regular (semanal, mensal, trimestral, semestral ou anual) e com um valor
estável. Consumos como a luz podem variar de valor. Depois calcula quanto pagas por
mês e por ano e avisa-te quando um preço sobe, quando há uma cobrança duplicada ou
quando um serviço deixou de ser cobrado.

**Luz.** Compara o teu consumo real com a tabela de ofertas, usando
*termo fixo × dias + preço por kWh × consumo*.

**Privacidade.** Os ficheiros são processados em memória e não são guardados.

Projeto de Ciência de Dados — código aberto.
"""
    )
