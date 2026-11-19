"""BillWatch — descobre quanto pagas todos os meses e onde podes poupar.

Correr localmente:  streamlit run app.py
"""

from __future__ import annotations

import re

import altair as alt
import pandas as pd
import streamlit as st

from contas.energia import POTENCIAS_PADRAO, carregar_ofertas, comparar, custo_periodo, ler_fatura_pdf
from contas.exemplo import extrato_csv_banco, gerar_extrato
from contas.extrato import (ExtratoNaoBancario, FormatoDesconhecido, LeituraDuvidosa, carregar_extrato,
                            diagnostico_tabela, juntar_extratos, ler_tabela, normalizar_com_mapa,
                            problemas_de_leitura, sugerir_mapa)
from contas.leitor_pdf import diagnostico_pdf
from contas.recorrentes import Parametros, detetar_recorrentes, euro, possiveis_subscricoes, preparar, resumo

AZUL = "#2a78d6"
FORMATOS = ["csv", "txt", "xlsx", "xls", "pdf"]

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


@st.cache_data(show_spinner="A ler o extrato…")
def _ler_extrato(conteudo: bytes, nome: str = "") -> pd.DataFrame:
    return carregar_extrato(conteudo, nome)


@st.cache_data(show_spinner=False)
def _diagnostico(conteudo: bytes, nome: str) -> dict:
    """Estrutura anónima de um ficheiro (para reportar problemas sem dados pessoais)."""
    if nome.lower().endswith(".pdf") or conteudo[:4] == b"%PDF":
        return diagnostico_pdf(conteudo)
    try:
        tabela = ler_tabela(conteudo, nome)
        return {"metodo": "tabela", "texto": diagnostico_tabela(tabela), "erro": ""}
    except Exception as erro:  # noqa: BLE001
        return {"metodo": "-", "texto": "", "erro": str(erro)}


@st.cache_data(show_spinner=False)
def _ofertas_base() -> pd.DataFrame:
    return carregar_ofertas()


# ---------------------------------------------------------------------------
# Leitura dos ficheiros (com plano B quando o formato não é reconhecido)
# ---------------------------------------------------------------------------

def _estrutura_anonima(f) -> None:
    d = _diagnostico(f.getvalue(), f.name)
    st.caption("Letras viram `x` e números viram `9`, por isso podes partilhar isto para corrigir o leitor "
               "sem revelar os teus dados. Confirma antes que não ficou nada pessoal visível.")
    resumo_pdf = ""
    if "cabecalho" in d:
        resumo_pdf = (f"método: {d.get('metodo')} · colunas: {d.get('cabecalho') or '—'} · "
                      f"linhas com data: {d.get('linhas_com_data', 0)} · movimentos: {d.get('movimentos', 0)}")
        if d.get("estrategias"):
            resumo_pdf += f"\nestratégias: {d['estrategias']}"
        if d.get("erro"):
            resumo_pdf += f"\nproblemas: {d['erro']}"
    st.code((resumo_pdf + "\n\n" if resumo_pdf else "") + (d.get("texto") or d.get("erro") or ""), language=None)


def _escolher_colunas(f, tabela: pd.DataFrame, mensagem: str = "não reconheci este formato sozinho.",
                      exigir_confirmacao: bool = False) -> pd.DataFrame | None:
    """Plano B: o utilizador diz que coluna é qual. Nunca fica preso num formato novo."""
    sugestao = sugerir_mapa(tabela)
    colunas = ["—"] + [str(c) for c in tabela.columns]
    k = f"mapa_{f.name}_{f.size}"

    def escolha(rotulo, chave_mapa, onde):
        atual = sugestao.get(chave_mapa)
        indice = colunas.index(atual) if atual in colunas else 0
        valor = onde.selectbox(rotulo, colunas, index=indice, key=f"{k}_{chave_mapa}")
        return None if valor == "—" else valor

    with st.container(border=True):
        st.markdown(f"**{f.name}** — {mensagem} Diz-me que coluna é qual:")
        st.dataframe(tabela.head(6), hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        mapa = {"data": escolha("Data", "data", c1), "descricao": escolha("Descrição", "descricao", c2)}
        duas = st.radio("Como aparece o valor?", ["Numa coluna (com - nas saídas)", "Em duas colunas: débito e crédito"],
                        index=1 if (sugestao.get("debito") or sugestao.get("credito")) and not sugestao.get("valor") else 0,
                        key=f"{k}_modo", horizontal=True).startswith("Em duas")
        c3, c4 = st.columns(2)
        if duas:
            mapa.update(debito=escolha("Débito (saídas)", "debito", c3), credito=escolha("Crédito (entradas)", "credito", c4))
        else:
            mapa.update(valor=escolha("Valor", "valor", c3), sinal=escolha("Coluna D/C (opcional)", "sinal", c4))
        inverter = st.checkbox("As saídas aparecem sem sinal - (inverter sinais)", key=f"{k}_inverter")
        if not (mapa["data"] and mapa["descricao"] and (mapa.get("valor") or mapa.get("debito") or mapa.get("credito"))):
            st.caption("Escolhe pelo menos a data, a descrição e o valor.")
            return None
        try:
            df = normalizar_com_mapa(tabela, mapa, inverter=inverter)
        except Exception:  # noqa: BLE001
            df = pd.DataFrame()
        if df.empty:
            st.error("Com estas colunas não encontrei movimentos com data e valor. Experimenta outras.")
            return None
        for problema in problemas_de_leitura(df):
            st.caption(f"⚠️ Atenção: {problema}.")
        if exigir_confirmacao and not st.checkbox(f"Usar estas colunas ({len(df)} movimentos)", key=f"{k}_ok"):
            return None
        st.success(f"✓ {len(df)} movimentos lidos com estas colunas.")
        return df


def _leitura_duvidosa(f, erro: LeituraDuvidosa) -> pd.DataFrame | None:
    """A leitura deu um resultado estranho: fica de fora, a não ser que o utilizador decida."""
    problemas = "\n".join(f"- {p}" for p in erro.problemas)
    if erro.tabela is not None:   # CSV/Excel: provavelmente as colunas foram mal escolhidas
        return _escolher_colunas(f, erro.tabela, f"a leitura automática não parece certa:\n{problemas}\n\n",
                                 exigir_confirmacao=True)
    with st.container(border=True):
        st.warning(f"**{f.name}** — a leitura deste ficheiro não parece certa, por isso ficou de fora "
                   f"da análise:\n{problemas}")
        st.caption("Isto costuma acontecer com documentos que não são o extrato da conta "
                   "(cripto, investimentos, faturas…) ou com PDFs num formato muito invulgar.")
        usar = st.checkbox("Usar este ficheiro mesmo assim", key=f"usar_{f.name}_{f.size}")
        with st.expander("Ver a estrutura anónima deste ficheiro"):
            _estrutura_anonima(f)
    return erro.extrato if usar else None


def ler_ficheiros(ficheiros) -> list[pd.DataFrame]:
    lidos = []
    for f in ficheiros:
        try:
            lidos.append(_ler_extrato(f.getvalue(), f.name))
        except ExtratoNaoBancario as erro:
            st.info(f"📈 **{f.name}** — {erro}")
        except LeituraDuvidosa as erro:
            df = _leitura_duvidosa(f, erro)
            if df is not None:
                lidos.append(df)
        except FormatoDesconhecido as erro:
            df = _escolher_colunas(f, erro.tabela)
            if df is not None:
                lidos.append(df)
        except ValueError as erro:
            st.error(f"**{f.name}** — {erro}")
            with st.expander("Ver a estrutura anónima deste ficheiro"):
                _estrutura_anonima(f)
        except Exception:  # noqa: BLE001  (nunca mostrar um erro técnico ao utilizador)
            st.error(f"**{f.name}** — não consegui ler este ficheiro. Confirma que é um extrato em CSV, "
                     "Excel ou PDF exportado do banco.")
            with st.expander("Ver a estrutura anónima deste ficheiro"):
                _estrutura_anonima(f)
    return lidos


def mostrar_diagnostico(extrato: pd.DataFrame, ficheiros) -> None:
    """Ajuda a perceber se o ficheiro foi bem lido, sem mostrar dados a ninguém."""
    with st.expander("🛠️ Os números parecem errados? Diagnóstico da leitura"):
        entradas, saidas = extrato[extrato["valor"] > 0], extrato[extrato["valor"] < 0]
        c1, c2 = st.columns(2)
        c1.metric("Entradas", f"{len(entradas)} · {euro(float(entradas['valor'].sum()))}")
        c2.metric("Saídas", f"{len(saidas)} · {euro(float(-saidas['valor'].sum()))}")
        st.caption("Compara com o teu extrato: as datas, os valores e os sinais (+/-) estão certos? "
                   "Se as entradas e saídas estiverem trocadas, usa **Inverter sinais** em *Afinar a deteção*.")
        st.dataframe(extrato[["data", "valor", "descricao"]].head(20), hide_index=True, width="stretch",
                     column_config={"data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                    "descricao": "Descrição",
                                    "valor": st.column_config.NumberColumn("Valor", format="%.2f €")})
        if ficheiros:
            nomes = [f.name for f in ficheiros]
            escolhido = st.selectbox("Estrutura anónima do ficheiro", nomes, key="diag_ficheiro") if len(nomes) > 1 else nomes[0]
            _estrutura_anonima(next(f for f in ficheiros if f.name == escolhido))


# ---------------------------------------------------------------------------
# Aba 1 — Subscrições
# ---------------------------------------------------------------------------

def _sem_sufixo(comerciante: str) -> str:
    """"Apple (iCloud/App Store) (0,99 €)" -> "Apple (iCloud/App Store)" (subgrupo por valor)."""
    return re.sub(r" \(\d[\d ]*,\d{2} €\)$", "", comerciante)


def modo_rapido(extrato: pd.DataFrame, dias_cobertos: int, confirmados: set[str] = frozenset()) -> None:
    """Para extratos curtos: mostra pagamentos a serviços conhecidos como possíveis subscrições."""
    if dias_cobertos < 55:
        st.info(f"O extrato cobre só {dias_cobertos + 1} dias. Para confirmar que um pagamento se repete "
                "preciso de pelo menos 2 a 3 meses — junta mais ficheiros para resultados completos.")
    possiveis = possiveis_subscricoes(extrato)
    if not possiveis.empty:
        # Não repetir o que já foi confirmado como pagamento fixo.
        possiveis = possiveis[~possiveis["comerciante"].isin(confirmados)]
    if possiveis.empty:
        return
    st.markdown("#### 🔎 Possíveis subscrições")
    st.caption("Pagamentos a serviços que costumam ser fixos (ou débitos diretos), ainda não confirmados por repetição.")
    st.metric("Total destes pagamentos no período", euro(float(possiveis["valor"].sum())))
    st.dataframe(
        possiveis, hide_index=True, width="stretch",
        column_config={
            "comerciante": "Serviço", "categoria": "Categoria",
            "valor": st.column_config.NumberColumn("Valor no período", format="%.2f €"),
            "n_pagamentos": "Pagamentos",
            "ultimo": st.column_config.DateColumn("Último", format="DD/MM/YYYY"),
            "nota": "Nota",
        },
    )


def pagina_subscricoes() -> None:
    st.subheader("Que pagamentos se repetem na tua conta?")
    st.write(
        "Exporta o extrato da tua conta em **CSV, Excel ou PDF** (na app ou no site do banco, normalmente em "
        "*Movimentos → Exportar*) com pelo menos 3 meses. Quanto mais meses, melhor. "
        "Se o banco só deixar exportar um mês de cada vez, **carrega vários ficheiros de uma vez** "
        "— a app junta-os e ignora movimentos repetidos."
    )
    ficheiros = st.file_uploader("Extratos bancários (CSV, Excel ou PDF)", type=FORMATOS, accept_multiple_files=True)
    col_a, col_b = st.columns(2)
    usar_exemplo = not ficheiros and col_a.toggle("Usar dados de exemplo", value=True)
    col_b.download_button("Descarregar extrato de exemplo", _csv_exemplo(), "extrato_exemplo.csv", "text/csv")
    st.caption("🔒 Os ficheiros são processados só em memória e não são guardados.")

    if ficheiros:
        lidos = ler_ficheiros(ficheiros)
        if not lidos:
            return
        extrato, n_lidos = juntar_extratos(lidos), len(lidos)
    elif usar_exemplo:
        extrato, n_lidos = _ler_extrato(_csv_exemplo()), 1
    else:
        return

    with st.expander("Afinar a deteção"):
        inverter = st.toggle("Inverter sinais (se as saídas aparecerem como entradas)", key="inverter_todos")
        p = Parametros(
            min_pagamentos=st.slider("Mínimo de pagamentos (comerciantes desconhecidos)", 2, 6, 3),
            regularidade_minima=st.slider("Regularidade mínima dos intervalos", 0.5, 1.0, 0.7, 0.05),
            variacao_maxima_valor=st.slider("Variação máxima do valor", 0.05, 0.5, 0.15, 0.05),
        )
    if inverter:
        extrato = extrato.assign(valor=-extrato["valor"])

    recorrentes = detetar_recorrentes(extrato, p)
    periodo = f"{extrato['data'].min():%d/%m/%Y} a {extrato['data'].max():%d/%m/%Y}"
    n_ficheiros = f" de {n_lidos} ficheiros" if n_lidos > 1 else ""
    st.caption(f"{len(extrato)} movimentos lidos{n_ficheiros}, de {periodo}.")

    mostrar_diagnostico(extrato, ficheiros)

    dias_cobertos = (extrato["data"].max() - extrato["data"].min()).days
    if recorrentes.empty or dias_cobertos < 55:
        confirmados = {_sem_sufixo(c) for c in recorrentes["comerciante"]} if not recorrentes.empty else set()
        modo_rapido(extrato, dias_cobertos, confirmados)
    if recorrentes.empty:
        if dias_cobertos >= 55:
            st.success(f"Não encontrei pagamentos fixos em {dias_cobertos // 30} meses de movimentos. "
                       "Se sabes que tens algum, procura-o em *Diagnóstico da leitura* e diz-me como aparece.")
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
    if r["poupanca_mensal"] > 0:
        st.caption(f"💰 Além disso, pões de lado **{euro(r['poupanca_mensal'])} por mês** em poupança ou "
                   "investimento (cofres, cripto, PPR…). Não conta como custo.")

    alertas = [(linha.comerciante, a) for linha in recorrentes.itertuples() for a in linha.alertas]
    if alertas:
        st.markdown("#### ⚠️ Alertas")
        for comerciante, alerta in alertas:
            st.warning(f"**{comerciante}** — {alerta}")

    st.markdown("#### Os teus pagamentos fixos")
    tabela = recorrentes.assign(
        confianca=(recorrentes["confianca"] * 100).round(),
        estado=[("Poupança" if poup else "Ativa") if ativa else "Parada"
                for ativa, poup in zip(recorrentes["ativa"], recorrentes["poupanca"])],
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

    ativas = recorrentes[recorrentes["ativa"] & ~recorrentes["poupanca"]]
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
        nome_base = _sem_sufixo(escolhido)
        st.dataframe(
            movimentos[movimentos["comerciante"] == nome_base][["data", "descricao", "montante"]],
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
        try:
            dados, texto = ler_fatura_pdf(pdf.getvalue())
        except Exception:  # noqa: BLE001  PDF protegido, digitalizado ou danificado
            from contas.energia import DadosFatura
            dados, texto = DadosFatura(), ""
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

**Formatos.** Extratos em CSV, Excel ou PDF de qualquer banco: colunas Débito/Crédito ou
um só valor com sinal, datas em qualquer formato, vários ficheiros de uma vez. Se um
formato não for reconhecido, a app pede-te para escolheres as colunas.

**Poupança à parte.** Transferências regulares para cofres, cripto ou PPR aparecem como
poupança e não contam como custo.

**Privacidade.** Os ficheiros são processados em memória e não são guardados.

Projeto de Ciência de Dados — código aberto.
"""
    )
