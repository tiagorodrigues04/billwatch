"""Página principal: carregar extratos e ver o talão das contas fixas."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from contas.partilhas import aplicar_partilhas
from contas.recorrentes import (DIAS_EXTRATO_CURTO, NOTA_EXPERIMENTAL, PERIODO, confirmados, euro, juntar_linhas,
                                linha_fixa, resumo, sem_sufixo)
from ui.componentes import Linha, barras, cabecalho, contagem, discreto, em_euros, passos, talao, talao_a_cinzento
from ui.dados import analisar, csv_exemplo, juntar, ler_extrato, movimentos
from ui.extratos import CARREGADOR, esquecer_ficheiros, ficheiros_guardados, guardar_ficheiros, publicar
from ui.leitura import ler_ficheiros, mostrar_leitura

FORMATOS = ["csv", "txt", "xlsx", "xls", "pdf"]
FREQUENCIA = {"Semanal": "por semana", "Mensal": "por mês", "Bimestral": "a cada 2 meses",
              "Trimestral": "a cada 3 meses", "Semestral": "a cada 6 meses", "Anual": "por ano"}
FREQUENCIAS = list(PERIODO)          # Semanal, Mensal, ..., Anual


def _data(d) -> str:
    return pd.Timestamp(d).strftime("%d/%m") if pd.notna(d) else ""


def _lista_de_nomes(nomes: list[str]) -> str:
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _nota_extra(r) -> str:
    """Notas a lápis: de onde veio a linha e quanto pagam os outros, se a conta é dividida."""
    notas = {"confirmado": ["confirmado por ti"], "manual": ["adicionado por ti"]}.get(getattr(r, "origem", ""), [])
    dividida = int(getattr(r, "dividida_por", 0) or 0)
    if dividida >= 2:
        notas.append(f"dividida por {dividida}: a tua parte é {euro(r.custo_real_mensal)}")
    elif getattr(r, "partilhado_por", None):
        quem = r.partilhado_por
        verbo = "paga-te" if len(quem) == 1 else "pagam-te"
        notas.append(f"{_lista_de_nomes(quem)} {verbo} {euro(r.partilhado_mensal)} por mês: "
                     f"a tua parte é {euro(r.custo_real_mensal)}")
    return "; ".join(notas)


def _blocos_do_talao(recorrentes: pd.DataFrame, possiveis: pd.DataFrame, curto: bool) -> tuple[list, str]:
    blocos: list = []
    rodape = ""
    if not recorrentes.empty:
        nao_custo = recorrentes["poupanca"] | recorrentes["entre_contas"]
        custos = recorrentes[~nao_custo]
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
            linhas.append(Linha(sem_sufixo(r.comerciante), euro(r.custo_mensal), "atencao" if r.alertas else "",
                                nota, nota_alerta=bool(r.alertas), nota_extra=_nota_extra(r)))
        for r in paradas.itertuples():
            desde = pd.Timestamp(r.ultimo_pagamento).strftime("%m/%Y")
            linhas.append(Linha(sem_sufixo(r.comerciante), euro(r.custo_mensal), "parado",
                                f"sem pagamentos desde {desde}, não entra no total"))
        r_ = resumo(recorrentes)
        if linhas:
            blocos.append((None, linhas))
            blocos.append(("---", []))
            totais = []
            if r_["partilhado_mensal"] > 0:
                totais += [Linha("Soma das contas", euro(r_["mensal_bruto"])),
                           Linha("Partes pagas por outros", "−" + euro(r_["partilhado_mensal"]))]
            totais += [Linha("Total por mês", euro(r_["mensal"]), "total"), Linha("Total por ano", euro(r_["anual"]))]
            blocos.append((None, totais))
        poupanca = recorrentes[recorrentes["poupanca"] & recorrentes["ativa"]]
        if not poupanca.empty:
            blocos.append(("Poupança e investimento, não conta como custo",
                           [Linha(r.comerciante, f"{euro(r.custo_mensal)}/mês") for r in poupanca.itertuples()]))
        entre = recorrentes[recorrentes["entre_contas"] & recorrentes["ativa"]]
        if not entre.empty:
            blocos.append(("Entre contas tuas, não conta como custo",
                           [Linha(r.comerciante, f"{euro(r.custo_mensal)}/mês") for r in entre.itertuples()]))
        proximos = ativas.dropna(subset=["proximo_previsto"]).sort_values("proximo_previsto").head(3)
        if not proximos.empty:
            rodape = "Próximos pagamentos: " + ", ".join(
                f"{sem_sufixo(r.comerciante)} a {_data(r.proximo_previsto)}" for r in proximos.itertuples()) + "."
    if not possiveis.empty:
        titulo = ("A confirmar: pagamentos a serviços que costumam ser fixos" if curto else
                  "A confirmar: pagamentos que só apareceram uma vez")
        linhas = []
        for r in possiveis.itertuples():
            experimental = r.nota == NOTA_EXPERIMENTAL
            nota = r.nota[0].lower() + r.nota[1:] if r.nota else \
                f"{r.n_pagamentos} pagamento{'s' if r.n_pagamentos > 1 else ''} no período"
            linhas.append(Linha(r.comerciante, euro(r.valor), "atencao" if experimental else "", nota,
                                nota_alerta=experimental))
        blocos.append((titulo, linhas))
    if not blocos:
        blocos.append((None, [Linha("Pagamentos fixos encontrados", "0")]))
    return blocos, rodape


def _linha_com_desfazer(texto: str, chave: str) -> bool:
    esquerda, direita = st.columns([3, 1], vertical_alignment="center")
    esquerda.caption(texto)
    return direita.button("Desfazer", key=chave, type="tertiary")


def _corrigir(recorrentes: pd.DataFrame, possiveis: pd.DataFrame, partilhas: pd.DataFrame):
    """O conteúdo do botão "Corrigir". Devolve (recorrentes, possiveis, partilhas aceites, divisões)."""
    estado = st.session_state
    manuais: list = estado.setdefault("manuais", [])
    escolhas: dict = estado.setdefault("confirmados", {})
    divisoes: dict = estado.setdefault("divisoes", {})
    retirar, adicionar, dividir, tuas = st.tabs(["Retirar", "Adicionar", "Dividir", "Contas tuas"])

    with retirar:
        if recorrentes.empty:
            st.caption("Ainda não há pagamentos fixos no talão.")
        else:
            excluir = st.multiselect("Retirar do talão o que não é um pagamento fixo",
                                     recorrentes["comerciante"].map(sem_sufixo).unique().tolist(),
                                     placeholder="Escolhe um ou mais", key="excluir")
            recorrentes = recorrentes[~recorrentes["comerciante"].map(sem_sufixo).isin(excluir)]

    with adicionar:
        escolhas = {c: f for c, f in escolhas.items() if c in set(possiveis["comerciante"])}
        estado["confirmados"] = escolhas
        pendentes = possiveis[~possiveis["comerciante"].isin(escolhas)]
        if not pendentes.empty:
            qual = st.selectbox("Confirmar um pagamento de \"A confirmar\"", pendentes["comerciante"].tolist(),
                                index=None, placeholder="Escolhe um pagamento", key="confirmar_qual")
            provavel = pendentes.loc[pendentes["comerciante"] == qual, "periodicidade"].iloc[0] if qual else "Mensal"
            freq = st.selectbox("Frequência", FREQUENCIAS, index=FREQUENCIAS.index(provavel),
                                key=f"confirmar_freq_{qual}")
            if st.button("Contar no total", disabled=qual is None, key="confirmar_botao"):
                escolhas[qual] = freq
                st.rerun()
        for c, f in list(escolhas.items()):
            if _linha_com_desfazer(f"{c}: confirmado, {FREQUENCIA[f]}", f"desfazer_confirmado_{c}"):
                del escolhas[c]
                st.rerun()
        with st.form("adicionar_manual", clear_on_submit=True, border=False):
            st.caption("Falta algum pagamento? Acrescenta-o à mão.")
            servico = st.text_input("Serviço", placeholder="Ex.: seguro do carro", key="manual_servico")
            valor = st.number_input("Valor (€)", min_value=0.0, step=1.0, format="%.2f", key="manual_valor")
            frequencia = st.selectbox("Frequência", FREQUENCIAS, index=FREQUENCIAS.index("Mensal"),
                                      key="manual_freq")
            if st.form_submit_button("Adicionar", key="manual_adicionar") and servico.strip() and valor > 0:
                manuais.append({"nome": servico.strip(), "valor": float(valor), "periodicidade": frequencia})
        for i, m in enumerate(list(manuais)):
            if _linha_com_desfazer(f"{m['nome']}: {euro(m['valor'])} {FREQUENCIA[m['periodicidade']]}",
                                   f"desfazer_manual_{i}"):
                manuais.pop(i)
                st.rerun()

    extra = confirmados(possiveis, escolhas) + [
        linha_fixa(m["nome"], "Adicionado por ti", m["valor"], m["periodicidade"]) for m in manuais]
    recorrentes = juntar_linhas(recorrentes, extra)
    possiveis = possiveis[~possiveis["comerciante"].isin(escolhas)]

    with dividir:
        aceites = []
        if not partilhas.empty:
            st.caption("Pessoas que te pagam parte de uma conta, todos os meses perto do mesmo dia:")
            for i, p in partilhas.iterrows():
                texto = f"{sem_sufixo(p.conta)}: {p.remetente} paga-te {euro(p.valor_mensal)} por mês"
                if st.checkbox(texto, value=True, key=f"partilha::{p.remetente}::{p.conta}"):
                    aceites.append(i)
        contas = [] if recorrentes.empty else recorrentes.loc[
            recorrentes["ativa"] & ~recorrentes["poupanca"] & ~recorrentes["entre_contas"], "comerciante"].tolist()
        conta = st.selectbox("Dividir uma conta à mão", contas, index=None, format_func=sem_sufixo,
                             placeholder="Escolhe uma conta", key="dividir_qual")
        pessoas = st.number_input("Quantas pessoas, contigo incluído", min_value=2, max_value=12, value=2,
                                  step=1, key="dividir_pessoas")
        if st.button("Dividir", disabled=conta is None, key="dividir_botao"):
            divisoes[conta] = int(pessoas)
            st.rerun()
        for c, n in list(divisoes.items()):
            if _linha_com_desfazer(f"{sem_sufixo(c)}: dividida por {n}", f"desfazer_divisao_{c}"):
                del divisoes[c]
                st.rerun()

    with tuas:
        st.text_input("O teu nome", key="nome_titular", placeholder="Ex.: Tiago Rodrigues",
                      help="Para reconhecer as transferências para outras contas no teu nome. "
                           "Fica só nesta sessão e não é guardado.")
        st.caption("Os carregamentos da Revolut, N26 ou Wise já não contam como custos, e as transferências "
                   "entre extratos de bancos diferentes também não. O nome serve para as transferências para "
                   "outra conta tua (\"TRF P/ ...\"), e para não confundir família com colegas de casa.")

    return recorrentes, possiveis, partilhas.loc[aceites], divisoes


# ---------------------------------------------------------------------------

cabecalho("Quanto pagas, todos os meses?",
          "Carrega os extratos do teu banco. O BillWatch encontra as subscrições e as contas fixas, "
          "soma-as e marca o que merece atenção.")
passos([("Exporta os extratos", "Na app ou no site do banco, em CSV, Excel ou PDF. Três meses ou mais."),
        ("Carrega-os aqui", "Podes juntar vários ficheiros, e até extratos de bancos diferentes."),
        ("Lê o teu talão", "Quanto pagas por mês, o que subiu de preço e o que podes cancelar.")])

carregados = st.file_uploader("Extratos do banco", type=FORMATOS, accept_multiple_files=True, key=CARREGADOR,
                              on_change=guardar_ficheiros, help="CSV, Excel ou PDF. Podes escolher vários de uma vez.")
ficheiros = carregados or ficheiros_guardados()
if ficheiros and not carregados:
    # Voltou de outra página: o carregador aparece vazio, mas os ficheiros continuam na sessão.
    guardados = st.container(horizontal=True, vertical_alignment="center", gap="small")
    guardados.caption(f"A usar {_lista_de_nomes([f.name for f in ficheiros])}, que carregaste antes.")
    guardados.button("Tirar", on_click=esquecer_ficheiros, type="tertiary", icon=":material/close:")
discreto("Os ficheiros são lidos em memória e nunca são guardados.")
linha = st.container(horizontal=True, vertical_alignment="center", gap="medium")
usar_exemplo = not ficheiros and linha.toggle("Ver com dados de exemplo", value=True)
linha.download_button("Descarregar o extrato de exemplo", csv_exemplo(), "extrato_exemplo.csv", "text/csv",
                      type="tertiary", icon=":material/download:")

avisos = st.container()      # ficheiros que não deu para ler (aparecem por cima do talão)
zona = st.empty()            # o talão a cinzento enquanto lê e analisa, e depois os resultados

if ficheiros:
    # Ficheiros novos levam tempo a ler (um PDF pode demorar segundos): mostra já a forma do talão.
    # Nos cliques seguintes está tudo em cache, por isso não se mostra (seria só um piscar).
    assinatura = tuple((f.file_id, f.size) for f in ficheiros)
    if st.session_state.get("_ficheiros_lidos") != assinatura:
        talao_a_cinzento(zona, f"A ler {len(ficheiros)} ficheiro{'s' if len(ficheiros) > 1 else ''}…")
    with avisos:
        lidos = ler_ficheiros(ficheiros)
    st.session_state["_ficheiros_lidos"] = assinatura
    extrato = juntar(lidos) if lidos else None
    n_lidos = len(lidos)
elif usar_exemplo:
    extrato, n_lidos = ler_extrato(csv_exemplo()), 1
else:
    extrato, n_lidos = None, 0

if extrato is None or extrato.empty:
    zona.empty()
    publicar(None, exemplo=False, ficheiros=0)
else:
    # Afinações (os controlos estão mais abaixo; aqui lê-se o valor escolhido)
    estado = st.session_state
    if estado.get("inverter_todos"):
        extrato = extrato.assign(valor=-extrato["valor"])
    publicar(extrato, exemplo=usar_exemplo and not ficheiros, ficheiros=n_lidos)   # para a página Supermercado
    nome = (estado.get("nome_titular") or "").strip()
    recorrentes, possiveis, partilhas = analisar(extrato, estado.get("p_min", 3), estado.get("p_reg", 0.7),
                                                 estado.get("p_var", 0.15), nome)
    dias = (extrato["data"].max() - extrato["data"].min()).days

    resultados = zona.container()   # substitui o talão a cinzento
    with resultados:
        st.divider()
        titulo, corrigir = st.columns([3, 1], vertical_alignment="bottom")
        titulo.subheader("O talão do exemplo" if usar_exemplo and not ficheiros else "O teu talão", anchor=False)
        with corrigir.popover("Corrigir", width="stretch"):
            recorrentes, possiveis, partilhas, divisoes = _corrigir(recorrentes, possiveis, partilhas)
        recorrentes = aplicar_partilhas(recorrentes, partilhas, divisoes)

        if dias < DIAS_EXTRATO_CURTO:
            st.info(f"Os extratos cobrem só {contagem(dias + 1, 'dia')}. Para confirmar que um pagamento se repete são precisos "
                    "2 a 3 meses: junta mais ficheiros para um talão completo.")

        periodo = f"{extrato['data'].min():%d/%m/%Y} a {extrato['data'].max():%d/%m/%Y}"
        origem = ("Exemplo com dados fictícios" if usar_exemplo and not ficheiros else
                  f"{contagem(len(extrato), 'movimento')} de {contagem(n_lidos, 'ficheiro')}")
        blocos, rodape_talao = _blocos_do_talao(recorrentes, possiveis, dias < DIAS_EXTRATO_CURTO)
        talao(["BillWatch", "Contas fixas", periodo, origem], blocos, rodape_talao)

        custos = recorrentes[recorrentes["ativa"] & ~recorrentes["poupanca"] & ~recorrentes["entre_contas"]] \
            if not recorrentes.empty else recorrentes
        if not custos.empty and custos["categoria"].nunique() > 1:
            st.subheader("Onde vai o dinheiro", anchor=False)
            discreto("Contas fixas por categoria, em euros por mês (a tua parte, nas contas divididas).")
            barras(custos.groupby("categoria", as_index=False)["custo_real_mensal"].sum(), "categoria",
                   "custo_real_mensal", "€ por mês")

        if not recorrentes.empty:
            with st.expander("Ver o detalhe de cada pagamento"):
                def _estado(r) -> str:
                    if r.poupanca:
                        return "Poupança"
                    if r.entre_contas:
                        return "Entre contas"
                    return "Ativa" if r.ativa else "Parada"

                tabela = recorrentes.assign(
                    comerciante=recorrentes["comerciante"].map(sem_sufixo),
                    confianca=(recorrentes["confianca"] * 100).round(),
                    estado=[_estado(r) for r in recorrentes.itertuples()])
                st.dataframe(
                    em_euros(tabela[["comerciante", "categoria", "periodicidade", "valor_tipico", "custo_anual",
                                     "custo_real_mensal", "proximo_previsto", "estado", "confianca"]],
                             ["valor_tipico", "custo_anual", "custo_real_mensal"]),
                    hide_index=True, width="stretch",
                    column_config={
                        "comerciante": "Serviço", "categoria": "Categoria", "periodicidade": "Frequência",
                        "valor_tipico": "Valor", "custo_anual": "Por ano", "custo_real_mensal": "A tua parte por mês",
                        "proximo_previsto": st.column_config.DateColumn("Próximo", format="DD/MM/YYYY"),
                        "estado": "Estado",
                        "confianca": st.column_config.ProgressColumn("Confiança", min_value=0, max_value=100,
                                                                     format="%d%%"),
                    },
                )
                escolhido = st.selectbox("Ver os movimentos de", tabela["comerciante"].unique().tolist())
                saidas = movimentos(extrato, nome)
                # Filtra também pela categoria: "Galp" (luz) e "Galp" (combustível) não se misturam.
                categorias = tabela.loc[tabela["comerciante"] == escolhido, "categoria"].unique()
                do_escolhido = saidas[(saidas["comerciante"] == escolhido) & saidas["categoria"].isin(categorias)]
                st.dataframe(em_euros(do_escolhido[["data", "descricao", "montante"]], ["montante"]),
                             hide_index=True, width="stretch",
                             column_config={"data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                            "descricao": "Descrição",
                                            "montante": "Valor"})

        with st.expander("Afinar a deteção"):
            st.toggle("Inverter sinais (se as saídas aparecerem como entradas)", key="inverter_todos")
            st.slider("Mínimo de pagamentos para um serviço desconhecido", 2, 6, 3, key="p_min")
            st.slider("Regularidade mínima entre pagamentos", 0.5, 1.0, 0.7, 0.05, key="p_reg")
            st.slider("Variação máxima do valor", 0.05, 0.5, 0.15, 0.05, key="p_var")

        mostrar_leitura(extrato, ficheiros)
