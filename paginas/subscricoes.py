"""Página principal: carregar extratos e ver o talão das contas fixas."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from contas.extrato import juntar_extratos
from contas.recorrentes import Parametros, detetar_recorrentes, euro, possiveis_subscricoes, preparar, resumo
from ui.componentes import Linha, barras, cabecalho, discreto, passos, talao
from ui.dados import csv_exemplo, ler_extrato
from ui.leitura import ler_ficheiros, mostrar_leitura

FORMATOS = ["csv", "txt", "xlsx", "xls", "pdf"]
FREQUENCIA = {"Semanal": "por semana", "Mensal": "por mês", "Bimestral": "a cada 2 meses",
              "Trimestral": "a cada 3 meses", "Semestral": "a cada 6 meses", "Anual": "por ano"}


def _sem_sufixo(comerciante: str) -> str:
    """"Apple (iCloud/App Store) (0,99 €)" -> "Apple (iCloud/App Store)" (subgrupo por valor)."""
    return re.sub(r" \(\d[\d ]*,\d{2} €\)$", "", comerciante)


def _data(d) -> str:
    return pd.Timestamp(d).strftime("%d/%m") if pd.notna(d) else ""


def _blocos_do_talao(recorrentes: pd.DataFrame, possiveis: pd.DataFrame) -> tuple[list, str]:
    blocos: list = []
    rodape = ""
    if not recorrentes.empty:
        custos = recorrentes[~recorrentes["poupanca"]]
        ativas = custos[custos["ativa"]].sort_values("custo_mensal", ascending=False)
        paradas = custos[~custos["ativa"]]
        linhas = []
        for r in ativas.itertuples():
            nota = (f"{euro(r.valor_tipico)} {FREQUENCIA.get(r.periodicidade, '')}"
                    if r.periodicidade != "Mensal" else "")
            if r.valor_variavel:
                nota = "média dos últimos meses, varia com o consumo"
            if r.alertas:
                nota = "; ".join(a[0].lower() + a[1:] for a in r.alertas) + (f" ({nota})" if nota else "")
            linhas.append(Linha(_sem_sufixo(r.comerciante), euro(r.custo_mensal), "atencao" if r.alertas else "",
                                nota, nota_alerta=bool(r.alertas)))
        for r in paradas.itertuples():
            desde = pd.Timestamp(r.ultimo_pagamento).strftime("%m/%Y")
            linhas.append(Linha(_sem_sufixo(r.comerciante), euro(r.custo_mensal), "parado",
                                f"sem pagamentos desde {desde}, não entra no total"))
        r_ = resumo(recorrentes)
        if linhas:
            blocos.append((None, linhas))
            blocos.append(("---", []))
            blocos.append((None, [Linha("Total por mês", euro(r_["mensal"]), "total"),
                                  Linha("Total por ano", euro(r_["anual"]))]))
        poupanca = recorrentes[recorrentes["poupanca"] & recorrentes["ativa"]]
        if not poupanca.empty:
            blocos.append(("Poupança e investimento, não conta como custo",
                           [Linha(r.comerciante, f"{euro(r.custo_mensal)}/mês") for r in poupanca.itertuples()]))
        proximos = ativas.dropna(subset=["proximo_previsto"]).sort_values("proximo_previsto").head(3)
        if not proximos.empty:
            rodape = "Próximos pagamentos: " + ", ".join(
                f"{_sem_sufixo(r.comerciante)} a {_data(r.proximo_previsto)}" for r in proximos.itertuples()) + "."
    if not possiveis.empty:
        blocos.append(("A confirmar: pagamentos a serviços que costumam ser fixos",
                       [Linha(r.comerciante, euro(r.valor),
                              "atencao" if r.nota else "",
                              r.nota[0].lower() + r.nota[1:] if r.nota else
                              f"{r.n_pagamentos} pagamento{'s' if r.n_pagamentos > 1 else ''} no período",
                              nota_alerta=bool(r.nota))
                        for r in possiveis.itertuples()]))
    if not blocos:
        blocos.append((None, [Linha("Pagamentos fixos encontrados", "0")]))
    return blocos, rodape


# ---------------------------------------------------------------------------

cabecalho("Quanto pagas, todos os meses?",
          "Carrega os extratos do teu banco. O BillWatch encontra as subscrições e as contas fixas, "
          "soma-as e marca o que merece atenção.")
passos([("Exporta os extratos", "Na app ou no site do banco, em CSV, Excel ou PDF. Três meses ou mais."),
        ("Carrega-os aqui", "Podes juntar vários ficheiros, se o banco só exportar mês a mês."),
        ("Lê o teu talão", "Quanto pagas por mês, o que subiu de preço e o que podes cancelar.")])

ficheiros = st.file_uploader("Extratos do banco", type=FORMATOS, accept_multiple_files=True,
                             help="CSV, Excel ou PDF. Podes escolher vários de uma vez.")
discreto("Os ficheiros são lidos em memória e nunca são guardados.")
linha = st.container(horizontal=True, vertical_alignment="center", gap="medium")
usar_exemplo = not ficheiros and linha.toggle("Ver com dados de exemplo", value=True)
linha.download_button("Descarregar o extrato de exemplo", csv_exemplo(), "extrato_exemplo.csv", "text/csv",
                      type="tertiary", icon=":material/download:")

if ficheiros:
    lidos = ler_ficheiros(ficheiros)
    extrato = juntar_extratos(lidos) if lidos else None
    n_lidos = len(lidos)
elif usar_exemplo:
    extrato, n_lidos = ler_extrato(csv_exemplo()), 1
else:
    extrato, n_lidos = None, 0

if extrato is not None and not extrato.empty:
    # Afinações (os controlos estão no fim da página; aqui lê-se o valor escolhido)
    estado = st.session_state
    if estado.get("inverter_todos"):
        extrato = extrato.assign(valor=-extrato["valor"])
    parametros = Parametros(min_pagamentos=estado.get("p_min", 3), regularidade_minima=estado.get("p_reg", 0.7),
                            variacao_maxima_valor=estado.get("p_var", 0.15))
    recorrentes = detetar_recorrentes(extrato, parametros)
    dias = (extrato["data"].max() - extrato["data"].min()).days

    possiveis = pd.DataFrame()
    if recorrentes.empty or dias < 55:
        possiveis = possiveis_subscricoes(extrato)
        if not possiveis.empty and not recorrentes.empty:
            confirmados = {_sem_sufixo(c) for c in recorrentes["comerciante"]}
            possiveis = possiveis[~possiveis["comerciante"].isin(confirmados)]

    st.divider()
    titulo, corrigir = st.columns([3, 1], vertical_alignment="bottom")
    titulo.subheader("O talão do exemplo" if usar_exemplo and not ficheiros else "O teu talão", anchor=False)
    if not recorrentes.empty:
        with corrigir.popover("Corrigir", width="stretch"):
            excluir = st.multiselect("Retirar do talão o que não é um pagamento fixo",
                                     recorrentes["comerciante"].map(_sem_sufixo).unique().tolist(),
                                     placeholder="Escolhe um ou mais", key="excluir")
        recorrentes = recorrentes[~recorrentes["comerciante"].map(_sem_sufixo).isin(excluir)]

    if dias < 55:
        st.info(f"Os extratos cobrem só {dias + 1} dias. Para confirmar que um pagamento se repete são precisos "
                "2 a 3 meses: junta mais ficheiros para um talão completo.")

    periodo = f"{extrato['data'].min():%d/%m/%Y} a {extrato['data'].max():%d/%m/%Y}"
    origem = ("Exemplo com dados fictícios" if usar_exemplo and not ficheiros else
              f"{len(extrato)} movimentos de {n_lidos} ficheiro{'s' if n_lidos > 1 else ''}")
    blocos, rodape_talao = _blocos_do_talao(recorrentes, possiveis)
    talao(["BillWatch", "Contas fixas", periodo, origem], blocos, rodape_talao)

    custos = recorrentes[recorrentes["ativa"] & ~recorrentes["poupanca"]] if not recorrentes.empty else recorrentes
    if not custos.empty and custos["categoria"].nunique() > 1:
        st.subheader("Onde vai o dinheiro", anchor=False)
        discreto("Contas fixas por categoria, em euros por mês.")
        barras(custos.groupby("categoria", as_index=False)["custo_mensal"].sum(), "categoria", "custo_mensal",
               "€ por mês")

    if not recorrentes.empty:
        with st.expander("Ver o detalhe de cada pagamento"):
            tabela = recorrentes.assign(
                comerciante=recorrentes["comerciante"].map(_sem_sufixo),
                confianca=(recorrentes["confianca"] * 100).round(),
                estado=[("Poupança" if poup else "Ativa") if ativa else "Parada"
                        for ativa, poup in zip(recorrentes["ativa"], recorrentes["poupanca"])])
            st.dataframe(
                tabela[["comerciante", "categoria", "periodicidade", "valor_tipico", "custo_anual",
                        "proximo_previsto", "estado", "confianca"]],
                hide_index=True, width="stretch",
                column_config={
                    "comerciante": "Serviço", "categoria": "Categoria", "periodicidade": "Frequência",
                    "valor_tipico": st.column_config.NumberColumn("Valor", format="%.2f €"),
                    "custo_anual": st.column_config.NumberColumn("Por ano", format="%.2f €"),
                    "proximo_previsto": st.column_config.DateColumn("Próximo", format="DD/MM/YYYY"),
                    "estado": "Estado",
                    "confianca": st.column_config.ProgressColumn("Confiança", min_value=0, max_value=100,
                                                                 format="%d%%"),
                },
            )
            escolhido = st.selectbox("Ver os movimentos de", tabela["comerciante"].unique().tolist())
            movimentos = preparar(extrato)
            st.dataframe(movimentos[movimentos["comerciante"] == escolhido][["data", "descricao", "montante"]],
                         hide_index=True, width="stretch",
                         column_config={"data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                        "descricao": "Descrição",
                                        "montante": st.column_config.NumberColumn("Valor", format="%.2f €")})

    with st.expander("Afinar a deteção"):
        st.toggle("Inverter sinais (se as saídas aparecerem como entradas)", key="inverter_todos")
        st.slider("Mínimo de pagamentos para um serviço desconhecido", 2, 6, 3, key="p_min")
        st.slider("Regularidade mínima entre pagamentos", 0.5, 1.0, 0.7, 0.05, key="p_reg")
        st.slider("Variação máxima do valor", 0.05, 0.5, 0.15, 0.05, key="p_var")

    mostrar_leitura(extrato, ficheiros)
