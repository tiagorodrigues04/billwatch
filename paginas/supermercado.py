"""Página do supermercado: quanto gastas, em que cadeias e quanto pesam as idas pequenas.

Usa os extratos carregados em Contas fixas (ui/extratos.py); sem eles, mostra o exemplo.
"""

from __future__ import annotations

import streamlit as st

from contas.recorrentes import euro
from contas.supermercados import CADEIAS, DIAS_POR_MES, LIMITE_IDA_PEQUENA, mais_barata, mudar_de_cadeia
from ui.componentes import Linha, cabecalho, contagem, colunas_por_mes, discreto, em_euros, talao
from ui.dados import csv_exemplo, indices_supermercados, ler_extrato, supermercado
from ui.extratos import extrato_publicado


def _numero(x: float) -> str:
    """12.46 -> "12,5"; 13.0 -> "13"."""
    texto = f"{x:.1f}".replace(".", ",")
    return texto.removesuffix(",0")


def _frequencia(idas_por_mes: float) -> str:
    """3.7 -> "3,7 idas por mês"; 1.0 -> "1 ida por mês"; 0.43 -> "1 ida a cada 2 meses"; 0 -> "só devoluções".

    Uma cadeia pode ter só devoluções (a compra foi antes do início do extrato): 0 idas.
    """
    if idas_por_mes <= 0:
        return "só devoluções"
    if idas_por_mes < 1 and round(1 / idas_por_mes) >= 2:
        return f"1 ida a cada {round(1 / idas_por_mes)} meses"
    numero = _numero(max(idas_por_mes, 1.0))
    return f"{numero} {'ida' if numero == '1' else 'idas'} por mês"


def _euros_redondos(x: float) -> str:
    return f"{x:.0f} €" if float(x).is_integer() else euro(x)


cabecalho("Quanto gastas no supermercado?",
          "Com os mesmos extratos das contas fixas: quanto gastas por mês, em que cadeias e quanto pesam as "
          "idas pequenas.")

publicado = extrato_publicado()
if publicado is not None and publicado.extrato is not None and not publicado.exemplo:
    extrato, exemplo = publicado.extrato, False
    discreto("Os extratos que carregaste em Contas fixas." if publicado.ficheiros > 1 else
             "O extrato que carregaste em Contas fixas.")
else:
    extrato, exemplo = ler_extrato(csv_exemplo()), True
    aviso = st.container(horizontal=True, vertical_alignment="center", gap="medium")
    aviso.caption("Exemplo com dados fictícios.")
    aviso.page_link("paginas/subscricoes.py", label="Carregar os teus extratos em Contas fixas",
                    icon=":material/upload_file:")

limite = float(st.session_state.get("limite_ida_pequena", LIMITE_IDA_PEQUENA))
tabela, resumo, meses = supermercado(extrato, limite)

if not (tabela["montante"] > 0).any():   # sem compras (vazio, ou só devoluções): não há médias a mostrar
    st.info("Não encontrei compras em supermercados nestes extratos. Reconheço estas cadeias: "
            + ", ".join(CADEIAS) + ".", icon=":material/shopping_cart:")
else:
    st.divider()
    st.subheader("O talão do exemplo" if exemplo else "O teu talão", anchor=False)
    if resumo.meses < 1:
        st.info(f"Os extratos cobrem só {contagem(round(resumo.meses * DIAS_POR_MES), 'dia')}: os valores por mês são uma estimativa.")

    compras_feitas = int((tabela["montante"] > 0).sum())
    linhas = [Linha(r.cadeia, euro(r.gasto_mensal),
                    nota=f"{_frequencia(r.idas_mensal)}, {euro(r.valor_medio)} em média" if r.idas_mensal > 0
                    else _frequencia(r.idas_mensal))
              for r in resumo.por_cadeia.itertuples()]
    blocos = [(None, linhas), ("---", []),
              (None, [Linha("Total por mês", euro(resumo.gasto_mensal), "total"),
                      Linha("Idas por mês", _numero(resumo.idas_mensal)),
                      Linha("Valor médio por ida", euro(resumo.valor_medio))])]
    if resumo.pequenas_mensal > 0:
        parte = resumo.pequenas_gasto_mensal / resumo.gasto_mensal if resumo.gasto_mensal > 0 else 0.0
        blocos.append((f"Idas pequenas, abaixo de {_euros_redondos(limite)}",
                       [Linha(_frequencia(resumo.pequenas_mensal), euro(resumo.pequenas_gasto_mensal),
                              nota=f"{parte:.0%} do que gastas no supermercado")]))
    talao(["BillWatch", "Supermercado",
           f"{extrato['data'].min():%d/%m/%Y} a {extrato['data'].max():%d/%m/%Y}",
           "Exemplo com dados fictícios" if exemplo else contagem(compras_feitas, "compra")],
          blocos, "Médias por mês. As devoluções descontam; as bombas de gasolina das cadeias ficam de fora.")

    if len(meses) >= 2:
        st.subheader("Mês a mês", anchor=False)
        discreto("O que gastaste no supermercado em cada mês completo dos extratos, em euros.")
        colunas_por_mes(meses, "gasto", "Gasto")

    # ---------- Mudar de cadeia compensa? ----------
    indices = indices_supermercados()
    referencia, ano, fonte = mais_barata(indices), int(indices["ano"].max()), str(indices["url"].iloc[0])
    comparacao = mudar_de_cadeia(resumo.por_cadeia, indices)
    no_estudo = comparacao.dropna(subset=["indice"])
    fora = comparacao.loc[comparacao["indice"].isna(), "cadeia"].tolist()

    st.subheader("Mudar de cadeia compensa?", anchor=False)
    if no_estudo.empty:
        st.markdown("As cadeias onde compras não entram no estudo de preços da DECO PROteste, por isso não dá "
                    "para comparar.")
    else:
        poupanca = float(no_estudo["poupanca_mensal"].sum())
        gasto_no_estudo = float(no_estudo["gasto_mensal"].sum())
        parte = poupanca / gasto_no_estudo if gasto_no_estudo > 0 else 0.0
        resposta = "Quase nada. " if parte < 0.01 else "Pouco. " if parte < 0.03 else ""
        if poupanca < 0.005:
            st.markdown(f"Das cadeias do estudo, só compras no {referencia}, que foi o supermercado online mais "
                        f"barato em {ano}.")
        else:
            st.markdown(f"{resposta}Se as tuas compras custassem o mesmo que no {referencia}, o supermercado "
                        f"online mais barato em {ano}, poupavas cerca de **{euro(poupanca)} por mês** "
                        f"({euro(poupanca * 12)} por ano).")
        st.dataframe(
            em_euros(no_estudo[["cadeia", "gasto_mensal", "indice", "poupanca_mensal"]],
                     ["gasto_mensal", "poupanca_mensal"]),
            hide_index=True, width="stretch",
            column_config={"cadeia": "Cadeia", "gasto_mensal": "Por mês",
                           "indice": st.column_config.NumberColumn("Índice", format="%d"),
                           "poupanca_mensal": "Poupança"})
    discreto(f"O índice da DECO PROteste para {ano} compara mais de 200 produtos nos supermercados online "
             f"(100 = o mais barato), sem portes, descontos em cartão ou em talão, nem promoções que obrigam a "
             f"comprar outros produtos. As lojas físicas podem ter outros preços e o teu carrinho não é o cabaz "
             f"do estudo: conta como ordem de grandeza."
             + (f" Fora do estudo: {', '.join(fora)}." if fora else ""))
    st.markdown(f"[Ver o estudo da DECO PROteste]({fonte})")

    with st.expander("Ver as compras"):
        st.dataframe(em_euros(tabela[["data", "cadeia", "descricao", "montante"]], ["montante"]),
                     hide_index=True, width="stretch",
                     column_config={"data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                    "cadeia": "Cadeia", "descricao": "Descrição", "montante": "Valor"})
        discreto("Reconheço estas cadeias: " + ", ".join(CADEIAS) + ". Se faltar a tua, avisa no GitHub.")

    with st.expander("Afinar"):
        st.slider("Uma ida conta como pequena abaixo de", 5, 25, int(LIMITE_IDA_PEQUENA), step=1, format="%d €",
                  key="limite_ida_pequena")
