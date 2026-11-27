"""Ler os ficheiros carregados, com plano B quando o formato não é reconhecido.

Nunca mostra um erro técnico: ou lê, ou pede ajuda ao utilizador (escolher colunas),
ou explica porque é que o ficheiro ficou de fora.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from contas.extrato import (ExtratoNaoBancario, FormatoDesconhecido, LeituraDuvidosa, normalizar_com_mapa,
                            problemas_de_leitura, sugerir_mapa)
from contas.recorrentes import euro

from .componentes import contagem, em_euros
from .dados import diagnostico, ler_extrato


def estrutura_anonima(f) -> None:
    d = diagnostico(f.getvalue(), f.name)
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


def escolher_colunas(f, tabela: pd.DataFrame, mensagem: str = "não reconheci este formato sozinho.",
                      exigir_confirmacao: bool = False) -> pd.DataFrame | None:
    """Plano B: o utilizador diz que coluna é qual. Nunca fica preso num formato novo."""
    sugestao = sugerir_mapa(tabela)
    colunas = ["—"] + [str(c) for c in tabela.columns]
    k = f"mapa_{f.file_id}"   # o file_id é único, mesmo com dois ficheiros com o mesmo nome

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
        if exigir_confirmacao and not st.checkbox(f"Usar estas colunas ({contagem(len(df), 'movimento')})", key=f"{k}_ok"):
            return None
        st.success(f"✓ {contagem(len(df), 'movimento')} lido{'' if len(df) == 1 else 's'} com estas colunas.")
        return df


def leitura_duvidosa(f, erro: LeituraDuvidosa) -> pd.DataFrame | None:
    """A leitura deu um resultado estranho: fica de fora, a não ser que o utilizador decida."""
    problemas = "\n".join(f"- {p}" for p in erro.problemas)
    if erro.tabela is not None:   # CSV/Excel: provavelmente as colunas foram mal escolhidas
        return escolher_colunas(f, erro.tabela, f"a leitura automática não parece certa:\n{problemas}\n\n",
                                 exigir_confirmacao=True)
    with st.container(border=True):
        st.warning(f"**{f.name}** — a leitura deste ficheiro não parece certa, por isso ficou de fora "
                   f"da análise:\n{problemas}")
        st.caption("Isto costuma acontecer com documentos que não são o extrato da conta "
                   "(cripto, investimentos, faturas…) ou com PDFs num formato muito invulgar.")
        usar = st.checkbox("Usar este ficheiro mesmo assim", key=f"usar_{f.file_id}")
        with st.expander("Ver a estrutura anónima deste ficheiro"):
            estrutura_anonima(f)
    return erro.extrato if usar else None


def ler_ficheiros(ficheiros) -> list[pd.DataFrame]:
    lidos = []
    for f in ficheiros:
        try:
            lidos.append(ler_extrato(f.getvalue(), f.name))
        except ExtratoNaoBancario as erro:
            st.info(f"📈 **{f.name}** — {erro}")
        except LeituraDuvidosa as erro:
            df = leitura_duvidosa(f, erro)
            if df is not None:
                lidos.append(df)
        except FormatoDesconhecido as erro:
            df = escolher_colunas(f, erro.tabela)
            if df is not None:
                lidos.append(df)
        except ValueError as erro:
            st.error(f"**{f.name}** — {erro}")
            with st.expander("Ver a estrutura anónima deste ficheiro"):
                estrutura_anonima(f)
        except Exception:  # noqa: BLE001  (nunca mostrar um erro técnico ao utilizador)
            st.error(f"**{f.name}** — não consegui ler este ficheiro. Confirma que é um extrato em CSV, "
                     "Excel ou PDF exportado do banco.")
            with st.expander("Ver a estrutura anónima deste ficheiro"):
                estrutura_anonima(f)
    return lidos


def mostrar_leitura(extrato: pd.DataFrame, ficheiros) -> None:
    """Ajuda a perceber se o ficheiro foi bem lido, sem mostrar dados a ninguém."""
    with st.expander("Os números parecem errados? Ver como o ficheiro foi lido"):
        entradas, saidas = extrato[extrato["valor"] > 0], extrato[extrato["valor"] < 0]
        c1, c2 = st.columns(2)
        c1.metric("Entradas", f"{len(entradas)} · {euro(float(entradas['valor'].sum()))}")
        c2.metric("Saídas", f"{len(saidas)} · {euro(float(-saidas['valor'].sum()))}")
        st.caption("Compara com o teu extrato: as datas, os valores e os sinais (+/-) estão certos? "
                   "Se as entradas e saídas estiverem trocadas, usa **Inverter sinais** em *Afinar a deteção*.")
        st.dataframe(em_euros(extrato[["data", "valor", "descricao"]].head(20), ["valor"]), hide_index=True,
                     width="stretch",
                     column_config={"data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                    "descricao": "Descrição",
                                    "valor": "Valor"})
        if ficheiros:
            indice = st.selectbox("Estrutura anónima do ficheiro", range(len(ficheiros)), key="diag_ficheiro",
                                  format_func=lambda i: ficheiros[i].name) if len(ficheiros) > 1 else 0
            estrutura_anonima(ficheiros[indice])
