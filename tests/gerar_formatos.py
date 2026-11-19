"""Gera uma coleção de extratos FICTÍCIOS em formatos diferentes, a partir dos mesmos movimentos.

Cada ficheiro imita uma forma real de os bancos exportarem extratos (separadores, números,
datas, colunas, PDFs com e sem grelha, ordem inversa, várias secções...). Os testes
confirmam que todos dão o mesmo resultado. Sempre que aparecer um formato novo que a
app não leia, acrescenta-se aqui uma imitação dele — e fica testado para sempre.

Correr:  python tests/gerar_formatos.py      (precisa de: pip install reportlab openpyxl)
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from contas.exemplo import gerar_extrato  # noqa: E402

PASTA = RAIZ / "tests" / "formatos"
MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def base() -> pd.DataFrame:
    df = gerar_extrato()
    return df[df["data"].between("2026-08-01", "2026-10-31")].reset_index(drop=True)


def cripto_semanal() -> pd.DataFrame:
    datas = pd.date_range("2026-08-03", "2026-10-26", freq="7D")
    return pd.DataFrame({"data": datas, "descricao": ["Compra de BTC"] * len(datas), "valor": [-25.0] * len(datas)})


def pt(v: float) -> str:          # 1234.5 -> "1.234,50"
    return f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def en(v: float) -> str:          # 1234.5 -> "1,234.50"
    return f"{abs(v):,.2f}"


def saldos(df: pd.DataFrame, inicial: float = 1500.0) -> list[float]:
    return list((df["valor"].cumsum() + inicial).round(2))


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def c01(df):  # banco PT clássico: ';', cp1252, linhas de título, Débito/Crédito
    linhas = ["Extrato de conta à ordem", "Conta: PT50 0000 0000 0000 0000 0000 0 (fictícia)", "",
              "Data Mov.;Data Valor;Descrição;Débito;Crédito;Saldo"]
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        d = r.data.strftime("%d-%m-%Y")
        linhas.append(f"{d};{d};{r.descricao};{pt(r.valor) if r.valor < 0 else ''};"
                      f"{pt(r.valor) if r.valor > 0 else ''};{pt(s)}")
    linhas += ["", "Saldo final;;;;;" + pt(saldos(df)[-1])]
    return "\n".join(linhas).encode("cp1252"), df


def c02(df):  # Montante com sinal, vírgula decimal, dd/mm/aaaa
    linhas = ["Data;Descrição;Montante;Saldo disponível"]
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        linhas.append(f"{r.data:%d/%m/%Y};{r.descricao};{'-' if r.valor < 0 else ''}{pt(r.valor)};{pt(s)}")
    return "\n".join(linhas).encode("utf-8"), df


def c03(df):  # inglês: ',', datas ISO, ponto decimal, aspas
    linhas = ["Date,Description,Amount,Balance"]
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        linhas.append(f'{r.data:%Y-%m-%d},"{r.descricao}",{r.valor:.2f},{s:.2f}')
    return "\n".join(linhas).encode("utf-8"), df


def c04(df):  # valor positivo + coluna D/C
    linhas = ["Data Lançamento;Data Valor;Descritivo;Valor;D/C;Saldo"]
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        linhas.append(f"{r.data:%d-%m-%Y};{r.data:%d-%m-%Y};{r.descricao};{pt(r.valor)};"
                      f"{'D' if r.valor < 0 else 'C'};{pt(s)}")
    return "\n".join(linhas).encode("utf-8"), df


def c05(df):  # sinal no fim ("9,99-"), datas com pontos
    linhas = ["Data;Movimento;Montante (EUR)"]
    for _, r in df.iterrows():
        linhas.append(f"{r.data:%d.%m.%Y};{r.descricao};{pt(r.valor)}{'-' if r.valor < 0 else ''}")
    return "\n".join(linhas).encode("utf-8"), df


def c06(df):  # Revolut (exportação de transações, EN), com revertido e moeda BTC
    linhas = ["Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance"]
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        tipo = "TOPUP" if r.valor > 0 else "CARD_PAYMENT"
        linhas.append(f"{tipo},Current,{r.data:%Y-%m-%d} 10:15:00,{r.data:%Y-%m-%d} 11:00:00,"
                      f"{r.descricao},{r.valor:.2f},0.00,EUR,COMPLETED,{s:.2f}")
    linhas.append("CARD_PAYMENT,Current,2026-09-14 10:00:00,,Loja Revertida,-50.00,0.00,EUR,REVERTED,")
    linhas.append("EXCHANGE,Crypto,2026-09-15 10:00:00,2026-09-15 10:00:01,Exchanged to BTC,0.00041,0,BTC,COMPLETED,0.00041")
    return "\n".join(linhas).encode("utf-8"), df


def c07(df):  # Revolut (extrato PT): resumo + secção conta + secção cripto
    cripto = cripto_semanal()
    linhas = ["Contas-correntes Resumos,,,,", "Produto,Saldo inicial,Dinheiro retirado,Dinheiro recebido,Saldo final",
              'Conta (Atual),"1.500,00 €","100,00 €","50,00 €","1.450,00 €"', ",,,,",
              "Transações da conta de 1 de agosto de 2026 a 31 de outubro de 2026,,,,",
              "Data,Descrição,Dinheiro retirado,Dinheiro recebido,Saldo"]
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        ret = f'"{pt(r.valor)} €"' if r.valor < 0 else ""
        rec = f'"{pt(r.valor)} €"' if r.valor > 0 else ""
        linhas.append(f'{r.data:%d/%m/%Y},{r.descricao},{ret},{rec},"{pt(s)} €"')
    linhas += [",,,,", "Transações da conta Cripto,,,,", "Data,Descrição,Dinheiro retirado,Dinheiro recebido,Saldo"]
    for (_, r), s in zip(cripto.iterrows(), saldos(cripto, 0)):
        linhas.append(f'{r.data:%d/%m/%Y},{r.descricao},"{pt(r.valor)} €",,"{pt(s)} €"')
    return "\n".join(linhas).encode("utf-8"), pd.concat([df, cripto])


def c08(df):  # tabulações, milhares com espaço não separável, salário > 1000 €
    extra = pd.DataFrame({"data": [pd.Timestamp("2026-09-30")], "descricao": ["SALARIO ESTAGIO"], "valor": [1250.0]})
    df = pd.concat([df, extra]).sort_values("data", kind="stable").reset_index(drop=True)
    linhas = ["Data\tDescrição\tValor\tSaldo"]
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        linhas.append(f"{r.data:%d-%m-%Y}\t{r.descricao}\t{'-' if r.valor < 0 else ''}"
                      f"{pt(r.valor).replace('.', chr(160))}\t{pt(s).replace('.', chr(160))}")
    return "\n".join(linhas).encode("utf-8"), df


# ---------------------------------------------------------------------------
# Excel / HTML
# ---------------------------------------------------------------------------

def x01(df):  # xlsx com títulos, datas reais e números reais, Débito/Crédito
    tabela = pd.DataFrame({
        "Data Movimento": df["data"], "Descrição": df["descricao"],
        "Débito": [-v if v < 0 else None for v in df["valor"]],
        "Crédito": [v if v > 0 else None for v in df["valor"]],
        "Saldo": saldos(df),
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame([["Movimentos de conta"], ["Período: 01-08-2026 a 31-10-2026"]]).to_excel(
            w, header=False, index=False)
        tabela.to_excel(w, startrow=3, index=False)
    return buf.getvalue(), df


def x02(df):  # ".xls" que é HTML
    tabela = pd.DataFrame({"Data": df["data"].dt.strftime("%d-%m-%Y"), "Descrição": df["descricao"],
                           "Montante": [("-" if v < 0 else "") + pt(v) for v in df["valor"]],
                           "Saldo": [pt(s) for s in saldos(df)]})
    html = "<html><head><meta charset='utf-8'></head><body><h3>Extrato</h3>" + tabela.to_html(index=False) + "</body></html>"
    return html.encode("utf-8"), df


def x03(df):  # datas como números série do Excel
    serie = (df["data"] - pd.Timestamp("1899-12-30")).dt.days
    tabela = pd.DataFrame({"Data": serie, "Descrição": df["descricao"], "Montante": df["valor"]})
    buf = io.BytesIO()
    tabela.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue(), df


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _pdf_texto(blocos, cabecalho_colunas, rodape=None, tamanho=7):
    """Desenha linhas de texto em colunas fixas (sem grelha), com cabeçalho repetido por página.

    blocos: lista de (titulo, linhas); cada linha = lista de (texto, x, alinhamento)
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pagina = [1]

    def nova_pagina():
        c.setFont("Helvetica", tamanho)
        return 800

    def cabecalho(y):
        c.setFont("Helvetica-Bold", tamanho)
        for texto, x, al in cabecalho_colunas:
            (c.drawRightString if al == "r" else c.drawString)(x, y, texto)
        c.setFont("Helvetica", tamanho)
        return y - 13

    def fim_pagina():
        if rodape:
            c.drawString(30, 30, f"{rodape} · Página {pagina[0]}")
        c.showPage()
        pagina[0] += 1

    y = nova_pagina()
    for titulo, linhas in blocos:
        if titulo:
            for t in titulo:
                c.drawString(30, y, t)
                y -= 12
        y = cabecalho(y)
        for linha in linhas:
            if y < 70:
                fim_pagina()
                y = cabecalho(nova_pagina())
            for texto, x, al in linha:
                if texto == "\n":
                    y -= 9
                    continue
                (c.drawRightString if al == "r" else c.drawString)(x, y, texto)
            y -= 11
        y -= 14
    fim_pagina()
    c.save()
    return buf.getvalue()


def p01(df):  # tabela com grelha, Débito/Crédito, cabeçalho repetido em cada página
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    linhas = [["Data Mov.", "Data Valor", "Descrição", "Débito", "Crédito", "Saldo"]]
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        d = r.data.strftime("%d-%m-%Y")
        linhas.append([d, d, r.descricao[:38], pt(r.valor) if r.valor < 0 else "", pt(r.valor) if r.valor > 0 else "", pt(s)])
    buf = io.BytesIO()
    t = Table(linhas, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 6)]))
    SimpleDocTemplate(buf, pagesize=A4).build([Paragraph("Extrato (fictício)", getSampleStyleSheet()["Title"]), t])
    return buf.getvalue(), df


def p02(df):  # texto sem grelha, Débito/Crédito em colunas, datas dd.mm.aa, saldo anterior
    linhas = []
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        linhas.append([(r.data.strftime("%d.%m.%y"), 30, "l"), (r.descricao[:45], 80, "l"),
                       (pt(r.valor), 400 if r.valor < 0 else 460, "r"), (pt(s), 530, "r")])
    pdf = _pdf_texto([(["EXTRATO COMBINADO (FICTÍCIO)", "Saldo anterior: 1.500,00"], linhas)],
                     [("Data", 30, "l"), ("Descritivo", 80, "l"), ("Débito", 400, "r"), ("Crédito", 460, "r"),
                      ("Saldo", 530, "r")])
    return pdf, df


def p03(df):  # estilo Revolut: mais recente primeiro, "5 out 2026", 2.ª linha, secções, rodapé
    cripto = cripto_semanal()

    def bloco(movs, inicial):
        s = saldos(movs, inicial)
        linhas = []
        for (_, r), saldo in reversed(list(zip(movs.iterrows(), s))):
            data = f"{r.data.day} {MESES_PT[r.data.month - 1]} {r.data.year}"
            linha = [(data, 30, "l"), (r.descricao[:40], 95, "l"),
                     (f"{pt(r.valor)} €", 390 if r.valor < 0 else 460, "r"), (f"{pt(saldo)} €", 540, "r")]
            if r.valor < 0 and "TRF" not in r.descricao:
                linha += [("\n", 0, "l"), ("Cartão: 535522******1234", 95, "l")]
            linhas.append(linha)
        return linhas

    colunas = [("Data", 30, "l"), ("Descrição", 95, "l"), ("Dinheiro retirado", 390, "r"),
               ("Dinheiro recebido", 460, "r"), ("Saldo", 540, "r")]
    pdf = _pdf_texto([(["Extrato de EUR", "Gerado em 19 nov 2026", "Resumo do saldo",
                        "Saldo inicial 1.500,00 €   Saldo final 1.450,00 €",
                        "Transações da conta de 1 ago 2026 a 31 out 2026"], bloco(df, 1500)),
                      (["Transações da conta Cripto"], bloco(cripto, 0))],
                     colunas, rodape="Revolut Bank UAB (fictício) · Relatório gerado em 19 nov 2026")
    return pdf, pd.concat([df, cripto])


def p04(df):  # só "Montante" com sinal, datas sem ano, sem saldo; ano no período
    linhas = [[(r.data.strftime("%d.%m"), 30, "l"), (r.descricao[:45], 75, "l"),
               (("-" if r.valor < 0 else "") + pt(r.valor), 470, "r")] for _, r in df.iterrows()]
    pdf = _pdf_texto([(["Extrato (fictício)", "Período: 01.08.2026 a 31.10.2026"], linhas)],
                     [("Data", 30, "l"), ("Descrição", 75, "l"), ("Montante", 470, "r")])
    return pdf, df


def p05(df):  # valor com marca D/C, data só na 1.ª linha de cada dia, saldo
    linhas, dia_anterior = [], None
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        data = r.data.strftime("%d-%m-%Y") if r.data != dia_anterior else ""
        dia_anterior = r.data
        linhas.append([(data, 30, "l"), (r.descricao[:45], 90, "l"), (pt(r.valor), 440, "r"),
                       ("D" if r.valor < 0 else "C", 446, "l"), (pt(s), 530, "r")])
    pdf = _pdf_texto([(["EXTRATO INTEGRADO (FICTÍCIO)"], linhas)],
                     [("Data", 30, "l"), ("Descrição", 90, "l"), ("Montante", 450, "r"), ("Saldo", 530, "r")])
    return pdf, df


def p06(df):  # inglês: "Oct 5, 2026", "Money out / Money in / Balance", €1,234.56
    linhas = []
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        data = f"{MESES_EN[r.data.month - 1]} {r.data.day}, {r.data.year}"
        linhas.append([(data, 30, "l"), (r.descricao[:42], 100, "l"),
                       (f"€{en(r.valor)}", 400 if r.valor < 0 else 470, "r"), (f"€{en(s)}", 545, "r")])
    pdf = _pdf_texto([(["Account statement (fictitious)", "Opening balance €1,500.00"], linhas)],
                     [("Date", 30, "l"), ("Description", 100, "l"), ("Money out", 400, "r"),
                      ("Money in", 470, "r"), ("Balance", 545, "r")])
    return pdf, df


def p08(df):  # células com 2 linhas centradas: a 1.ª linha da descrição fica POR CIMA da data
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    def cabecalho(y):
        c.setFont("Helvetica-Bold", 6)
        for t, x, al in [("Data", 30, "l"), ("Descrição", 90, "l"), ("Débito", 420, "r"),
                         ("Crédito", 480, "r"), ("Saldo", 550, "r")]:
            (c.drawRightString if al == "r" else c.drawString)(x, y, t)
        c.setFont("Helvetica", 6)
        return y - 22

    y = cabecalho(800)
    for (_, r), s in zip(df.iterrows(), saldos(df)):
        if y < 60:
            c.showPage()
            y = cabecalho(800)
        palavras = r.descricao.split()
        c.drawString(90, y + 4.5, " ".join(palavras[:3]))
        if palavras[3:]:
            c.drawString(90, y - 4.5, " ".join(palavras[3:]))
        c.drawString(30, y, r.data.strftime("%d/%m/%Y"))
        c.drawRightString(420 if r.valor < 0 else 480, y, pt(r.valor))
        c.drawRightString(550, y, pt(s))
        y -= 18
    c.showPage()
    c.save()
    return buf.getvalue(), df


GERADORES = {
    "c01_pt_debito_credito.csv": c01, "c02_montante_virgula.csv": c02, "c03_en_amount.csv": c03,
    "c04_valor_dc.csv": c04, "c05_sinal_no_fim.csv": c05, "c06_revolut_en.csv": c06,
    "c07_revolut_extrato_pt.csv": c07, "c08_tabulacoes_milhares.csv": c08,
    "x01_cabecalho.xlsx": x01, "x02_html.xls": x02, "x03_datas_serie.xlsx": x03,
    "p01_grelha.pdf": p01, "p02_texto_colunas.pdf": p02, "p03_revolut.pdf": p03,
    "p04_sem_ano_sem_saldo.pdf": p04, "p05_marcas_dc.pdf": p05, "p06_ingles.pdf": p06,
    "p08_celulas_centradas.pdf": p08,
}


# ---------------------------------------------------------------------------
# Ficheiros que NÃO são extratos de conta, ou que não se conseguem ler com confiança
# ---------------------------------------------------------------------------

_CRIPTO = [("SOL", 115.77, 0.79), ("BTC", 79350.12, 1.59), ("ETH", 1735.40, 2.11), ("SOL", 115.77, 0.79),
           ("XRP", 2.21, 5.00), ("BTC", 79350.12, 3.17), ("ADA", 0.68, 2.00), ("SOL", 115.77, 2.32)]


def p07_cripto():  # extrato de cripto (compras de moedas): colunas Quantidade / Preço / Valor
    linhas = []
    for i, (moeda, preco, valor) in enumerate(_CRIPTO * 4):
        dia = f"{13 + i // 6:02d}/03/2025"
        linhas.append([(dia, 30, "l"), (moeda, 90, "l"), ("Compra", 130, "l"), (f"{valor / preco:.8f}".replace(".", ","), 260, "r"),
                       (f"{pt(preco)} €", 340, "r"), (f"{pt(valor)} €", 410, "r"), ("0,02 €", 470, "r")])
    pdf = _pdf_texto([(["Extrato de criptomoedas (fictício)", "Período: 01/01/2025 - 31/12/2025"], linhas)],
                     [("Data", 30, "l"), ("Símbolo", 90, "l"), ("Tipo", 130, "l"), ("Quantidade", 260, "r"),
                      ("Preço", 340, "r"), ("Valor", 410, "r"), ("Comissões", 470, "r")])
    return pdf


def c09_cripto():  # exportação CSV de cripto (estilo Revolut)
    linhas = ["Symbol,Type,Quantity,Price,Value,Fees,Date"]
    for i, (moeda, preco, valor) in enumerate(_CRIPTO):
        linhas.append(f"{moeda},BUY,{valor / preco:.8f},EUR {preco:.2f},EUR {valor:.2f},EUR 0.02,2025-03-{13 + i:02d} 08:15:00")
    return "\n".join(linhas).encode("utf-8")


def p09_ilegivel():  # o sintoma que apareceu num PDF real: linhas com data e só números, sem descrição
    linhas = []
    for i, (moeda, preco, valor) in enumerate(_CRIPTO * 4):
        dia = f"{13 + i // 6:02d}/03/2025"
        linhas.append([(dia, 30, "l"), (f"{pt(preco)} €", 340, "r"), (f"{pt(valor)} €", 420, "r")])
    return _pdf_texto([(["Documento (fictício)"], linhas)], [("Data", 30, "l"), ("Valor", 340, "r"), ("Crédito", 420, "r")])


ESPECIAIS = {
    "p07_cripto.pdf": (p07_cripto, "nao_bancario"),
    "c09_cripto.csv": (c09_cripto, "nao_bancario"),
    "p09_ilegivel.pdf": (p09_ilegivel, "duvidosa"),
}


def main() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    esperado = {}
    for nome, gerador in GERADORES.items():
        conteudo, movimentos = gerador(base())
        (PASTA / nome).write_bytes(conteudo)
        esperado[nome] = {"n": int(len(movimentos)), "total": round(float(movimentos["valor"].sum()), 2),
                          "entradas": int((movimentos["valor"] > 0).sum())}
        print(f"{nome:32} {esperado[nome]}")
    (PASTA / "esperado.json").write_text(json.dumps(esperado, indent=2, ensure_ascii=False))
    especiais = {}
    for nome, (gerador, resultado) in ESPECIAIS.items():
        (PASTA / nome).write_bytes(gerador())
        especiais[nome] = resultado
        print(f"{nome:32} -> {resultado}")
    (PASTA / "especiais.json").write_text(json.dumps(especiais, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
