from pathlib import Path

import pandas as pd
import pytest

from contas.catalogo import identificar
from contas.energia import carregar_ofertas, comparar, extrair_dados_texto, ler_fatura_pdf
from contas.exemplo import extrato_csv_banco, gerar_extrato
from contas.extrato import carregar_extrato, chave_comerciante, converter_numero
from contas.recorrentes import detetar_recorrentes, resumo

RAIZ = Path(__file__).resolve().parent.parent


# --- extrato ---------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("1.234,56", 1234.56), ("-12,99", -12.99), ("12.99", 12.99), ("€ 7,99", 7.99),
    ("1,234.56", 1234.56), ("", None), ("abc", None),
])
def test_converter_numero(texto, esperado):
    assert converter_numero(texto) == esperado


def test_le_formato_banco_com_cabecalho_e_debito_credito():
    df = carregar_extrato(extrato_csv_banco(gerar_extrato()))
    assert list(df.columns) == ["data", "descricao", "valor"]
    assert (df["valor"] < 0).any() and (df["valor"] > 0).any()
    assert df["data"].is_monotonic_increasing


def test_le_formato_simples_com_montante():
    csv = "Date,Description,Amount\n2026-01-05,NETFLIX.COM,-7.99\n2026-02-05,NETFLIX.COM,-7.99\n"
    df = carregar_extrato(csv.encode())
    assert df["valor"].tolist() == [-7.99, -7.99]


def test_chave_comerciante_remove_ruido():
    assert chave_comerciante("COMPRA 4521 NETFLIX.COM 866-579 12/03") == "NETFLIX"
    assert chave_comerciante("TRF RENDA QUARTO REF 770487") == "RENDA QUARTO"


def test_catalogo():
    assert identificar("DD MEO SA ENT 12345") == ("MEO", "Telecomunicações")
    assert identificar("GOOGLE *YOUTUBEPREMIUM") == ("YouTube Premium", "Streaming")
    assert identificar("COMPRA HOMEOPATIA") is None  # "MEO" dentro de outra palavra não conta


@pytest.mark.parametrize("descricao, esperado", [
    ("DD GALP ENERGIA SA", ("Galp", "Energia")),
    ("SDD GALP 123456", ("Galp", "Energia")),          # débito direto da Galp = conta da luz/gás
    ("DD AGUAS DO PORTO EM", ("Água", "Energia")),
    ("MEO ENERGIA", ("MEO Energia", "Energia")),        # a chave mais comprida ganha
    ("APPLE.COM/BILL", ("Apple (iCloud/App Store)", "Software e nuvem")),
    ("PAYPAL *SPOTIFYAB", ("Spotify", "Streaming")),
    ("Pagamento OK! Teleseguros", ("OK! Teleseguros", "Seguros")),
    ("COMPRA CROSSFIT GYM COIMBRA", ("Ginásio", "Ginásio")),
    ("TRF RENDA QUARTO REF 770487", ("Renda", "Casa")),
])
def test_catalogo_reconhece(descricao, esperado):
    assert identificar(descricao) == esperado


@pytest.mark.parametrize("descricao", [
    "COMPRA 1234 GALP OLIVAIS LISBOA",   # combustível, não é a conta da luz
    "COMPRA REPSOL A1 KM 20",
    "GOOGLE PLAY APPS",                  # compra de uma app
    "STEAM PURCHASE",                    # compra de um jogo
    "COMPRA GYM SHARK STORE",            # loja de roupa, não é ginásio
    "COMPRA DISNEYLAND PARIS",
    "RESTAURANTE AGUAS FURTADAS",
    "COMPRA LOJA DAS PRENDAS",           # "RENDA" dentro de outra palavra
    "COMPRA 7-ELEVEN",
    "MB WAY PARA JOAO SEGURO",           # apelido de uma pessoa, não é um seguro
])
def test_catalogo_nao_confunde(descricao):
    assert identificar(descricao) is None


def test_combustivel_na_galp_nao_e_conta_fixa():
    datas = pd.date_range("2026-01-03", periods=10, freq="30D")
    valores = [-31.2, -48.9, -40.0, -52.3, -35.7, -44.1, -38.8, -50.5, -33.0, -46.2]
    extrato = pd.DataFrame({"data": datas, "descricao": "COMPRA 1234 GALP OLIVAIS", "valor": valores})
    assert detetar_recorrentes(extrato).empty


# --- recorrentes -------------------------------------------------------------

@pytest.fixture(scope="module")
def recorrentes():
    return detetar_recorrentes(gerar_extrato()).set_index("comerciante")


def test_encontra_subscricoes_e_ignora_ruido(recorrentes):
    for nome in ["Netflix", "Spotify", "ChatGPT", "Fitness Hut", "MEO", "EDP", "Fidelidade", "Renda"]:
        assert nome in recorrentes.index, nome
    for ruido in ["Continente", "Cafe Santa", "Uber"]:
        assert not any(ruido in c for c in recorrentes.index), ruido


def test_periodicidades(recorrentes):
    assert recorrentes.loc["Netflix", "periodicidade"] == "Mensal"
    assert recorrentes.loc["Fidelidade", "periodicidade"] == "Semestral"
    assert recorrentes.loc["Fidelidade", "custo_mensal"] == pytest.approx(84.50 * 2 / 12, abs=0.01)


def test_alertas(recorrentes):
    assert any("subiu 25%" in a for a in recorrentes.loc["Netflix", "alertas"])
    assert not recorrentes.loc["Disney+", "ativa"]
    assert any("duplic" in a or "10 dias" in a for a in recorrentes.loc["Spotify", "alertas"])
    assert recorrentes.loc["EDP", "valor_variavel"]


def test_resumo_so_conta_ativas(recorrentes):
    r = resumo(recorrentes.reset_index())
    ativas = recorrentes[recorrentes["ativa"]]
    assert r["mensal"] == pytest.approx(ativas["custo_mensal"].sum(), abs=0.01)
    assert r["n_ativas"] == len(ativas)


def test_extrato_sem_recorrentes():
    df = pd.DataFrame({"data": pd.to_datetime(["2026-01-01", "2026-03-17"]),
                       "descricao": ["LOJA A", "LOJA B"], "valor": [-10.0, -55.0]})
    assert detetar_recorrentes(df).empty


# --- energia -----------------------------------------------------------------

def test_le_fatura_pdf_exemplo():
    dados, _ = ler_fatura_pdf((RAIZ / "dados" / "fatura_exemplo.pdf").read_bytes())
    assert dados.consumo_kwh == 185
    assert dados.potencia_kva == 4.6
    assert dados.preco_kwh == pytest.approx(0.158)
    assert dados.termo_fixo_dia == pytest.approx(0.265)
    assert dados.dias == 31
    assert dados.total == pytest.approx(47.61)


def test_extrair_texto_vazio():
    assert extrair_dados_texto("sem números aqui").campos_encontrados() == []


def test_comparar_ordena_e_calcula_poupanca():
    res = comparar(200, 6.9, carregar_ofertas(), custo_atual=60.0, dias=30)
    assert res["custo_mensal"].is_monotonic_increasing
    linha = res.iloc[0]
    esperado = (linha["termo_fixo_eur_dia"] * 30 + linha["preco_kwh"] * 200) * 30.4 / 30
    assert linha["custo_mensal"] == pytest.approx(esperado, abs=0.01)
    assert linha["poupanca_anual"] == pytest.approx((60 * 30.4 / 30 - linha["custo_mensal"]) * 12, abs=0.05)


# --- vários ficheiros e modo rápido ----------------------------------------

def test_juntar_extratos_mensais_com_sobreposicao():
    from contas.extrato import juntar_extratos
    completo = gerar_extrato()
    # Ficheiros mensais que se sobrepõem 3 dias (como acontece ao exportar à mão)
    partes = []
    for periodo in completo["data"].dt.to_period("M").unique():
        ini = periodo.start_time - pd.Timedelta(days=3)
        fim = periodo.end_time
        partes.append(completo[(completo["data"] >= ini) & (completo["data"] <= fim)])
    junto = juntar_extratos(partes)
    assert len(junto) == len(completo)
    assert junto["valor"].sum() == pytest.approx(completo["valor"].sum())


def test_juntar_mantem_movimentos_iguais_no_mesmo_ficheiro():
    from contas.extrato import juntar_extratos
    dia = pd.Timestamp("2026-03-01")
    a = pd.DataFrame({"data": [dia, dia], "descricao": ["CAFE", "CAFE"], "valor": [-1.2, -1.2]})
    assert len(juntar_extratos([a, a.iloc[:1]])) == 2


def test_modo_rapido_um_mes():
    from contas.recorrentes import possiveis_subscricoes
    completo = gerar_extrato()
    um_mes = completo[completo["data"].dt.to_period("M") == pd.Period("2026-10", "M")]
    assert detetar_recorrentes(um_mes).empty
    possiveis = possiveis_subscricoes(um_mes)
    assert {"Netflix", "Spotify", "MEO", "EDP"} <= set(possiveis["comerciante"])
    assert not any("Continente" in c for c in possiveis["comerciante"])


def test_duplicado_nao_esconde_subscricao_em_extrato_curto():
    completo = gerar_extrato()
    tres_meses = completo[completo["data"].between("2026-08-01", "2026-10-31")]
    r = detetar_recorrentes(tres_meses).set_index("comerciante")
    assert "Spotify" in r.index
    assert any("10 dias" in a for a in r.loc["Spotify", "alertas"])


# --- Excel -------------------------------------------------------------------

def _tabela_banco():
    return pd.DataFrame({
        "Data Movimento": ["05-10-2026", "05-11-2026"],
        "Data Valor": ["05-10-2026", "05-11-2026"],
        "Descrição": ["COMPRA NETFLIX.COM", "COMPRA NETFLIX.COM"],
        "Montante": ["-9,99", "-9,99"],
        "Saldo": ["100,00", "90,01"],
    })


def test_le_xlsx_com_linhas_antes_da_tabela():
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame([["Extrato de conta"], ["IBAN PT50 fictício"], [None]]).to_excel(w, header=False, index=False)
        _tabela_banco().to_excel(w, startrow=4, index=False)
    df = carregar_extrato(buf.getvalue(), "movimentos.xlsx")
    assert df["valor"].tolist() == [-9.99, -9.99]
    assert df["data"].dt.month.tolist() == [10, 11]


def test_le_xls_que_e_html():
    html = "<html><body><p>Movimentos</p>" + _tabela_banco().to_html(index=False) + "</body></html>"
    df = carregar_extrato(html.encode("utf-8"), "movimentos.xls")
    assert df["valor"].tolist() == [-9.99, -9.99]


# --- PDF ---------------------------------------------------------------------

@pytest.mark.parametrize("ficheiro", ["extrato_tabela.pdf", "extrato_texto.pdf"])
def test_le_extrato_pdf(ficheiro):
    """Dois layouts fictícios: tabela com grelha, e texto solto com Débito/Crédito em colunas."""
    df = carregar_extrato((RAIZ / "tests" / "fixtures" / ficheiro).read_bytes(), ficheiro)
    assert len(df) == 64
    assert df["valor"].sum() == pytest.approx(-681.42)
    assert {"Netflix", "Spotify", "MEO"} <= set(detetar_recorrentes(df)["comerciante"])


# --- descrições no estilo do Novo Banco (nomes e refs inventados) --------------

def test_descricoes_estilo_novo_banco():
    from contas.extrato import corrigir_texto_pdf
    assert corrigir_texto_pdf("Cobran(cid:231)a Sdd") == "Cobrança Sdd"
    assert chave_comerciante("Compra Mb Cartºo **** 123* Pingo Doce Coimbra") == "PINGO DOCE"
    assert chave_comerciante("Compra Mb Cartão **** 123* Mercadona") == "MERCADONA"
    assert chave_comerciante("Cobrança Sdd Ginasio Xpto Unipessoal,Lda Adc 00011122233") == "GINASIO XPTO"
    assert chave_comerciante("Trf Imediata Sepa+ De Maria Exemplo") == "MARIA EXEMPLO"


def test_debito_direto_estilo_novo_banco_e_detetado():
    datas = pd.to_datetime(["2026-07-14", "2026-08-14", "2026-09-15", "2026-10-14"])
    df = pd.DataFrame({
        "data": list(datas) * 2,
        "descricao": ["Cobran(cid:231)a Sdd Xpto Fitness Unipessoal,Lda Adc 0001112223"] * 4
                     + ["Compra Mb Cartºo **** 123* Pingo Doce Coimbra"] * 4,
        "valor": [-7.98] * 4 + [-12.40, -3.10, -27.85, -8.00],
    })
    from contas.extrato import normalizar_extrato
    r = detetar_recorrentes(normalizar_extrato(df))
    assert r["comerciante"].tolist() == ["Xpto Fitness"]
    assert r.iloc[0]["custo_mensal"] == 7.98


def test_subscricao_escondida_entre_compras_do_mesmo_comerciante():
    # iCloud 0,99 € todos os meses + apps compradas na mesma "APPLE.COM/BILL"
    datas_icloud = pd.to_datetime(["2026-07-09", "2026-08-09", "2026-09-09", "2026-10-09"])
    compras = pd.to_datetime(["2026-07-21", "2026-08-02", "2026-09-27"])
    df = pd.DataFrame({
        "data": list(datas_icloud) + list(compras),
        "descricao": ["APPLE.COM/BILL"] * 7,
        "valor": [-0.99] * 4 + [-12.99, -4.49, -16.99],
    })
    r = detetar_recorrentes(df)
    assert len(r) == 1
    assert r.iloc[0]["comerciante"].startswith("Apple")
    assert r.iloc[0]["valor_tipico"] == 0.99


def test_periodo_experimental():
    from contas.recorrentes import possiveis_subscricoes
    df = pd.DataFrame({"data": pd.to_datetime(["2026-11-05"]), "descricao": ["MICROSOFT*365"], "valor": [-1.0]})
    assert "experimental" in possiveis_subscricoes(df).iloc[0]["nota"]


def test_transferencias_redondas_para_pessoas_nao_sao_subscricao():
    # Pagamentos de 20 € a pessoas diferentes pela mesma app, quase todas as semanas
    datas = pd.date_range("2026-07-04", periods=16, freq="7D")
    df = pd.DataFrame({
        "data": list(datas) + [datas[5], datas[9]],
        "descricao": ["PAG APP TERCEIROS"] * 18,
        "valor": [-20.0] * 16 + [-35.0, -7.5],
    })
    df.loc[[3, 8], "valor"] = -12.0
    assert detetar_recorrentes(df).empty


# --- Revolut -----------------------------------------------------------------

REVOLUT_EN = """Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance
CARD_PAYMENT,Current,2026-10-05 14:22:11,2026-10-06 09:01:02,Netflix,-9.99,0.00,EUR,COMPLETED,120.01
CARD_PAYMENT,Current,2026-11-05 14:22:11,2026-11-06 09:01:02,Netflix,-9.99,0.00,EUR,COMPLETED,110.02
CARD_PAYMENT,Current,2026-11-07 10:00:00,,Pingo Doce,-15.00,0.00,EUR,REVERTED,
TOPUP,Current,2026-11-08 10:00:00,2026-11-08 10:00:01,Top-up by *1234,50.00,0.00,EUR,COMPLETED,160.02
"""

REVOLUT_PT = """Tipo,Produto,Data de início,Data de conclusão,Descrição,Montante,Comissão,Moeda,Estado,Saldo
Pagamento com cartão,Atual,2026-10-05 14:22:11,2026-10-06 09:01:02,Spotify,-6.99,0.00,EUR,CONCLUÍDA,120.01
Pagamento com cartão,Atual,2026-11-05 14:22:11,2026-11-06 09:01:02,Spotify,-6.99,0.00,EUR,CONCLUÍDA,113.02
Pagamento com cartão,Atual,2026-11-07 10:00:00,,Mercadona,-15.00,0.00,EUR,REVERTIDA,
"""


@pytest.mark.parametrize("csv, descricao", [(REVOLUT_EN, "Netflix"), (REVOLUT_PT, "Spotify")])
def test_revolut(csv, descricao):
    df = carregar_extrato(csv.encode())
    assert df["data"].dt.strftime("%Y-%m-%d").tolist()[:2] == ["2026-10-05", "2026-11-05"]
    assert "Pingo Doce" not in df["descricao"].tolist() and "Mercadona" not in df["descricao"].tolist()
    assert df[df["descricao"] == descricao]["valor"].tolist() == [df.iloc[0]["valor"]] * 2
    assert descricao in detetar_recorrentes(df)["comerciante"].tolist()


REVOLUT_EXTRATO_PT = """Contas-correntes Resumos,,,,
Produto,Saldo inicial,Dinheiro retirado,Dinheiro recebido,Saldo final
Conta (Atual),"100,00 €","40,98 €","50,00 €","109,02 €"
,,,,
Transações da conta de 1 de outubro de 2026 a 30 de novembro de 2026,,,,
Data,Descrição,Dinheiro retirado,Dinheiro recebido,Saldo
05/10/2026,Netflix,"9,99 €",,"90,01 €"
08/10/2026,Carregamento de *1234,,"50,00 €","140,01 €"
05/11/2026,Netflix,"9,99 €",,"130,02 €"
,,,,
Transações da conta Cripto,,,,
Data,Descrição,Dinheiro retirado,Dinheiro recebido,Saldo
12/10/2026,Compra de BTC,"21,00 €",,"109,02 €"
"""


def test_revolut_extrato_com_seccoes():
    df = carregar_extrato(REVOLUT_EXTRATO_PT.encode())
    assert len(df) == 4  # 3 da conta + 1 de cripto; o resumo fica de fora
    assert df["valor"].sum() == pytest.approx(-9.99 + 50 - 9.99 - 21)
    assert df["data"].min() == pd.Timestamp("2026-10-05")
    assert "Netflix" in detetar_recorrentes(df)["comerciante"].tolist()


def test_ler_ofertas_do_excel_portugues():
    """CSV do Excel em português: ';' a separar e vírgula decimal; nomes de colunas com acentos ou maiúsculas."""
    from contas.energia import comparar, ler_ofertas
    csv_pt = ("Comercializadora;Tarifário;potencia_kva;termo_fixo_eur_dia;preco_kwh\n"
              "A;Simples;4,6;0,2555;0,1420\nB;Simples;4,6;0,2600;0,1380\nC;Simples;;0,2;0,1\n").encode("cp1252")
    ofertas = ler_ofertas(csv_pt)
    assert list(ofertas["comercializadora"]) == ["A", "B"]          # a linha sem potência sai
    assert ofertas["preco_kwh"].tolist() == [0.142, 0.138]
    assert len(comparar(200, 4.6, ofertas)) == 2


def test_mudar_de_cadeia_nao_da_poupanca_negativa():
    import pandas as pd

    from contas.supermercados import mudar_de_cadeia
    por_cadeia = pd.DataFrame({"cadeia": ["Continente", "Pingo Doce"], "gasto_mensal": [100.0, -5.0]})
    indices = pd.DataFrame({"cadeia": ["Continente", "Pingo Doce"], "indice": [100, 110]})
    assert mudar_de_cadeia(por_cadeia, indices)["poupanca_mensal"].min() >= 0
