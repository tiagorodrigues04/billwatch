"""Leitura de extratos bancários em PDF.

Um PDF não tem "colunas" — só palavras soltas com coordenadas na página. Por isso
fazemos duas tentativas e ficamos com a melhor:

A) Tabelas desenhadas (com linhas/grelha): o pdfplumber extrai-as como tabelas e
   tratamo-las como um CSV.

B) Palavras com posição (funciona em qualquer PDF com texto):
   1. agrupar as palavras em linhas (mesma altura na página);
   2. encontrar a linha de cabeçalho ("Data | Descrição | Débito | Crédito | Saldo")
      e guardar a posição horizontal de cada coluna de valores;
   3. cada linha que começa por uma data é um movimento; cada valor monetário da
      linha pertence à coluna de cabeçalho mais próxima — é assim que sabemos se é
      débito, crédito ou saldo;
   4. linhas sem data logo abaixo de um movimento são a continuação da descrição
      (ou um 2.º movimento do mesmo dia, se tiverem valor);
   5. o saldo serve de verificação: saldo atual - saldo anterior = movimento com sinal.
      Funciona com o extrato em ordem cronológica ou do mais recente para o mais antigo.

Formatos de data aceites: 05-10-2026, 05/10/26, 2026-10-05, 5 out 2026,
5 de out. de 2026, Oct 5, 2026, e datas sem ano (05.10) com o ano tirado do período.
"""

from __future__ import annotations

import io
import re
import statistics
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .extrato import SEPARADOR_DETALHE, normalizar_extrato, tabela_de_linhas
from .texto import anonimizar, chave, converter_numero, corrigir_texto_pdf, e_valor, ler_data_inicio

# Palavras de cabeçalho -> tipo de coluna
_PAL_DATA = {"data", "date", "datas"}
_PAL_DESC = {"descricao", "descritivo", "description", "movimento", "detalhe", "detalhes",
             "designacao", "historico", "transacao", "transaccao", "details", "operacao"}
_PAL_DEBITO = {"debito", "debitos", "debit", "debits", "retirado", "retirados", "saida", "saidas",
               "withdrawal", "withdrawals", "levantamentos"}
_PAL_CREDITO = {"credito", "creditos", "credit", "credits", "recebido", "recebidos", "entrada",
                "entradas", "deposito", "depositos", "deposit", "deposits"}
_PAL_VALOR = {"montante", "montantes", "valor", "valores", "amount", "importancia", "quantia"}
_PAL_SALDO = {"saldo", "saldos", "balance"}
_PREFIXOS = {"dinheiro", "money", "paid", "valor"}
_DUAS_PALAVRAS = {("money", "out"): "debito", ("paid", "out"): "debito",
                  ("money", "in"): "credito", ("paid", "in"): "credito"}

_RESUMO = re.compile(r"\b(total|totais|subtotal|a transportar|transporte|resumo|saldo final|"
                     r"saldo disponivel|saldo contabilistico|closing balance)\b")
_SALDO_INICIAL = re.compile(r"\b(saldo (inicial|anterior|de abertura|transitado|transportado)|"
                            r"opening balance|balance brought forward)\b")


@dataclass
class Palavra:
    texto: str
    x0: float
    x1: float
    top: float

    @property
    def centro(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Movimento:
    data: date
    tem_ano: bool
    descricao: str
    valor: float | None            # com sinal, se já se souber
    absoluto: float
    sinal_conhecido: bool
    saldo: float | None
    pagina: int
    top: float
    x_descricao: float
    linhas_extra: int = 0
    origem: str = "colunas"
    tipo_coluna: str | None = None   # debito / credito / valor / None (sem cabeçalho)
    sinal_escrito: int = 0           # -1 se o valor vinha com "-", +1 com "+", 0 sem sinal


@dataclass
class _Estado:
    ancoras: list = field(default_factory=list)       # [(tipo, x0, x1)]
    cabecalho: str = ""


# ---------------------------------------------------------------------------
# Palavras -> linhas
# ---------------------------------------------------------------------------

def _linhas_da_pagina(pagina) -> list[list[Palavra]]:
    palavras = pagina.extract_words(x_tolerance=1.5, y_tolerance=2.5, keep_blank_chars=False)
    palavras = [Palavra(corrigir_texto_pdf(w["text"]), w["x0"], w["x1"], w["top"]) for w in palavras]
    palavras.sort(key=lambda p: (p.top, p.x0))
    linhas: list[list[Palavra]] = []
    for p in palavras:
        if linhas and abs(p.top - linhas[-1][0].top) <= 2.5:
            linhas[-1].append(p)
        else:
            linhas.append([p])
    return [_juntar_valores(sorted(l, key=lambda p: p.x0)) for l in linhas]


def _juntar_valores(linha: list[Palavra]) -> list[Palavra]:
    """Junta pedaços de um mesmo valor: "1 234,56" · "9,99 €" · "- 9,99" · "€ 9,99"."""
    resultado: list[Palavra] = []
    for p in linha:
        if resultado:
            ant = resultado[-1]
            perto = p.x0 - ant.x1 < 4.5
            junta = False
            if perto and re.fullmatch(r"[-+]?€?\d{1,3}", ant.texto) and re.fullmatch(r"\d{3}([.,]\d{2})?(€|EUR)?", p.texto):
                junta = True                                   # milhares separados por espaço
            elif perto and p.texto in ("€", "EUR") and e_valor(ant.texto):
                junta = True                                   # 9,99 €
            elif perto and ant.texto in ("-", "+", "€", "-€", "+€") and e_valor(p.texto):
                junta = True                                   # - 9,99  /  € 9,99
            if junta:
                resultado[-1] = Palavra(f"{ant.texto} {p.texto}" if ant.texto not in ("-", "+") else ant.texto + p.texto,
                                        ant.x0, p.x1, ant.top)
                continue
        resultado.append(p)
    return resultado


def _normal(texto: str) -> str:
    return chave(texto).strip(".:;,()[]|")


# ---------------------------------------------------------------------------
# Cabeçalho e colunas
# ---------------------------------------------------------------------------

def _ancoras_cabecalho(linha: list[Palavra]) -> list | None:
    """Se a linha for um cabeçalho de movimentos, devolve as colunas e as suas posições."""
    if len(linha) < 3:
        return None
    nomes = [_normal(p.texto) for p in linha]
    ancoras = []
    tem_data = False
    for i, nome in enumerate(nomes):
        anterior = nomes[i - 1] if i else ""
        tipo = _DUAS_PALAVRAS.get((anterior, nome))
        # "Dinheiro retirado", "Money out": a coluna começa na 1.ª palavra
        x0 = linha[i - 1].x0 if (tipo or anterior in _PREFIXOS) and i else linha[i].x0
        if tipo is None:
            if nome in _PAL_DATA:
                tem_data = True
                continue
            if nome in _PAL_VALOR and anterior in _PAL_DATA:
                continue                                       # "Data Valor" é uma data
            tipo = ("debito" if nome in _PAL_DEBITO else "credito" if nome in _PAL_CREDITO else
                    "valor" if nome in _PAL_VALOR else "saldo" if nome in _PAL_SALDO else None)
        if tipo:
            if ancoras and ancoras[-1][0] == tipo and i and ancoras[-1][2] == linha[i - 1].x1:
                continue
            ancoras.append((tipo, x0, linha[i].x1))
    if tem_data and any(a[0] in ("debito", "credito", "valor") for a in ancoras):
        return ancoras
    return None


def _coluna_do_valor(p: Palavra, ancoras: list) -> str | None:
    melhor, distancia = None, float("inf")
    for tipo, x0, x1 in ancoras:
        d = min(abs(p.centro - (x0 + x1) / 2), abs(p.x1 - x1), abs(p.x0 - x0))
        if d < distancia:
            melhor, distancia = tipo, d
    return melhor


# ---------------------------------------------------------------------------
# Linhas -> movimentos
# ---------------------------------------------------------------------------

def _palavras_da_data(linha: list[Palavra]) -> tuple[date, bool, int] | None:
    """Data no início da linha: (data, tem_ano, nº de palavras que ocupa)."""
    texto = " ".join(p.texto for p in linha)
    lido = ler_data_inicio(texto)
    if not lido:
        return None
    data, consumidos, tem_ano = lido
    n, pos = 0, 0
    for p in linha:
        if pos >= consumidos:
            break
        pos += len(p.texto) + 1
        n += 1
    return data, tem_ano, n


def _ler_palavras(pdf) -> tuple[list[Movimento], dict]:
    estado = _Estado()
    movimentos: list[Movimento] = []
    saldo_inicial = None
    info = {"cabecalho": "", "linhas_com_data": 0, "paginas": len(pdf.pages)}
    pendente = None   # data + descrição numa linha, valores na linha seguinte

    for n_pagina, pagina in enumerate(pdf.pages):
        linhas = _linhas_da_pagina(pagina)
        alturas = [b[0].top - a[0].top for a, b in zip(linhas, linhas[1:]) if b[0].top > a[0].top]
        altura = statistics.median(alturas) if alturas else 12.0
        ultimo_na_pagina: Movimento | None = None

        for linha in linhas:
            texto_norm = _normal(" ".join(p.texto for p in linha))
            ancoras = _ancoras_cabecalho(linha)
            if ancoras:
                estado.ancoras = ancoras
                estado.cabecalho = " | ".join(t for t, _, _ in ancoras)
                info["cabecalho"] = estado.cabecalho
                ultimo_na_pagina, pendente = None, None
                continue

            lida = _palavras_da_data(linha)
            resto = linha[lida[2]:] if lida else linha
            # "Data Valor": uma 2.ª data logo a seguir à 1.ª
            if lida and resto:
                segunda = _palavras_da_data(resto)
                if segunda and (segunda[1] or not lida[1]):
                    resto = resto[segunda[2]:]
            valores = [p for p in resto if e_valor(p.texto)]
            # Marcas D/C só contam logo a seguir a um valor ("9,99 D"), não no meio da descrição.
            marcas = {i for i, p in enumerate(resto) if p.texto.upper() in ("D", "C", "DB", "CR")
                      and i and e_valor(resto[i - 1].texto)}
            palavras = [p for i, p in enumerate(resto) if not e_valor(p.texto) and i not in marcas
                        and p.texto not in ("€", "EUR", "-", "+")]
            descricao = " ".join(p.texto for p in palavras).strip()

            if _SALDO_INICIAL.search(texto_norm) and valores:
                saldo_inicial = converter_numero(valores[-1].texto)
                continue
            if _RESUMO.search(texto_norm) and not lida:
                continue

            perto = (ultimo_na_pagina is not None and 0 < linha[0].top - ultimo_na_pagina.top <= altura * 2.6)

            if lida:
                info["linhas_com_data"] += 1
                if not valores:
                    pendente = (lida, descricao, linha[0].top, palavras[0].x0 if palavras else linha[0].x1)
                    continue
                data, tem_ano = lida[0], lida[1]
                x_desc = palavras[0].x0 if palavras else linha[0].x1
            elif valores and pendente is not None and linha[0].top - pendente[2] <= altura * 2.2:
                (data, tem_ano, _), desc_ant, _, x_desc = pendente
                descricao = f"{desc_ant} {descricao}".strip()
            elif valores and perto and descricao and "=" not in texto_norm:
                data, tem_ano = ultimo_na_pagina.data, ultimo_na_pagina.tem_ano   # 2.º movimento do mesmo dia
                x_desc = ultimo_na_pagina.x_descricao
            else:
                # Continuação da descrição do movimento anterior (ex.: Revolut "Para: Netflix")
                if (not valores and descricao and perto and ultimo_na_pagina.linhas_extra < 2
                        and palavras and palavras[0].x0 >= ultimo_na_pagina.x_descricao - 8
                        and not _RESUMO.search(texto_norm)):
                    ultimo_na_pagina.descricao += SEPARADOR_DETALHE + descricao
                    ultimo_na_pagina.linhas_extra += 1
                    ultimo_na_pagina.top = linha[0].top
                continue
            pendente = None

            # Que valor é o movimento e qual é o saldo?
            mov_txt, saldo_txt, tipo_mov = None, None, None
            if estado.ancoras:
                for p in valores:
                    tipo = _coluna_do_valor(p, estado.ancoras)
                    if tipo == "saldo" and saldo_txt is None:
                        saldo_txt = p.texto
                    elif tipo in ("debito", "credito", "valor") and mov_txt is None:
                        mov_txt, tipo_mov = p.texto, tipo
                if mov_txt is None and len(valores) >= 2:
                    mov_txt, saldo_txt = valores[-2].texto, valores[-1].texto
                elif mov_txt is None:
                    mov_txt = valores[0].texto
            else:
                mov_txt = valores[-2].texto if len(valores) >= 2 else valores[0].texto
                saldo_txt = valores[-1].texto if len(valores) >= 2 else None

            bruto = converter_numero(mov_txt)
            if bruto is None:
                continue
            explicito = mov_txt.strip().startswith(("-", "+", "(")) or mov_txt.strip().endswith("-")
            marca = next((resto[i].texto.upper() for i in sorted(marcas)), None)
            if tipo_mov == "debito":
                valor, conhecido = -abs(bruto), True
            elif tipo_mov == "credito":
                valor, conhecido = abs(bruto), True
            elif marca:
                valor, conhecido = (-abs(bruto) if marca in ("D", "DB") else abs(bruto)), True
            elif explicito:
                valor, conhecido = bruto, True
            else:
                valor, conhecido = None, False

            m = Movimento(data=data, tem_ano=tem_ano, descricao=descricao, valor=valor, absoluto=abs(bruto),
                          sinal_conhecido=conhecido, saldo=converter_numero(saldo_txt) if saldo_txt else None,
                          pagina=n_pagina, top=linha[0].top, x_descricao=x_desc, tipo_coluna=tipo_mov,
                          sinal_escrito=(-1 if bruto < 0 else 1) if explicito else 0)
            movimentos.append(m)
            ultimo_na_pagina = m

    info["saldo_inicial"] = saldo_inicial
    return movimentos, info


# ---------------------------------------------------------------------------
# Sinais pelo saldo e anos em falta
# ---------------------------------------------------------------------------

def _sinais_pelo_saldo(movimentos: list[Movimento], saldo_inicial: float | None) -> None:
    """Usa a variação do saldo para descobrir (ou confirmar) se cada valor entrou ou saiu.

    Testa as duas ordens possíveis (cronológica e do mais recente para o mais antigo)
    e fica com a que explica mais movimentos.
    """
    if sum(m.saldo is not None for m in movimentos) < max(2, len(movimentos) // 2):
        return

    def sinais(ordem: list[Movimento], inicial) -> dict[int, float]:
        resultado, anterior = {}, inicial
        for m in ordem:
            if m.saldo is not None and anterior is not None:
                diferenca = round(m.saldo - anterior, 2)
                if abs(abs(diferenca) - m.absoluto) <= 0.011:
                    resultado[id(m)] = 1.0 if diferenca > 0 else -1.0
            if m.saldo is not None:
                anterior = m.saldo
        return resultado

    direto = sinais(movimentos, saldo_inicial)
    inverso = sinais(list(reversed(movimentos)), saldo_inicial)
    melhor = direto if len(direto) >= len(inverso) else inverso
    if len(melhor) < len(movimentos) * 0.3:
        return

    # Se as colunas e o saldo discordarem muito, o saldo ganha (as colunas podem estar mal alinhadas).
    conhecidos = [m for m in movimentos if m.sinal_conhecido and id(m) in melhor]
    discordam = sum((m.valor > 0) != (melhor[id(m)] > 0) for m in conhecidos)
    confiar_no_saldo = conhecidos and discordam > len(conhecidos) * 0.3
    for m in movimentos:
        if id(m) in melhor and (not m.sinal_conhecido or confiar_no_saldo):
            m.valor, m.sinal_conhecido = m.absoluto * melhor[id(m)], True
            m.origem = "saldo"


def _sinais_pela_convencao(movimentos: list[Movimento]) -> None:
    """Numa coluna única de valores, se o banco escreve "-" nas saídas e nunca "+",
    então um valor sem sinal é uma entrada (e o contrário se só usar "+")."""
    coluna_unica = [m for m in movimentos if m.tipo_coluna in ("valor", None)]
    negativos = sum(m.sinal_escrito < 0 for m in coluna_unica)
    positivos = sum(m.sinal_escrito > 0 for m in coluna_unica)
    if negativos >= 3 and positivos == 0:
        sinal = 1.0
    elif positivos >= 3 and negativos == 0:
        sinal = -1.0
    else:
        return
    for m in coluna_unica:
        if not m.sinal_conhecido:
            m.valor, m.sinal_conhecido, m.origem = m.absoluto * sinal, True, "convencao"


def _completar_anos(movimentos: list[Movimento], texto_completo: str) -> None:
    """Datas sem ano (ex.: "05.10"): o ano vem das datas completas que aparecem no PDF (período)."""
    if all(m.tem_ano for m in movimentos):
        return
    completas = []
    for m in re.finditer(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", texto_completo):
        try:
            completas.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    completas += [m.data for m in movimentos if m.tem_ano]
    hoje = date.today()
    inicio = min(completas) if completas else None
    fim = max(completas) if completas else hoje
    anos = sorted({d.year for d in completas} | {fim.year}) if completas else [hoje.year]
    for m in movimentos:
        if m.tem_ano:
            continue
        candidatos = []
        for ano in set(anos) | {a - 1 for a in anos} | {a + 1 for a in anos}:
            try:
                d = date(ano, m.data.month, m.data.day)
            except ValueError:
                continue
            if inicio:
                distancia = 0 if inicio <= d <= fim else min(abs((d - inicio).days), abs((d - fim).days))
            else:
                distancia = (d - hoje).days if d > hoje else 0
            candidatos.append((distancia, -ano, d))
        if candidatos:
            m.data = min(candidatos)[2]
            m.tem_ano = True


# ---------------------------------------------------------------------------
# Tentativa A: tabelas desenhadas
# ---------------------------------------------------------------------------

def _ler_tabelas(pdf) -> pd.DataFrame | None:
    linhas = []
    for pagina in pdf.pages:
        for tabela in pagina.extract_tables() or []:
            linhas += [[corrigir_texto_pdf(c) if c else c for c in l] for l in tabela]
    if not linhas:
        return None
    try:
        resultado = normalizar_extrato(tabela_de_linhas(linhas))
    except ValueError:
        return None
    return resultado if len(resultado) else None


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def _abrir(conteudo: bytes):
    import pdfplumber
    try:
        return pdfplumber.open(io.BytesIO(conteudo))
    except Exception as erro:  # PDF protegido por palavra-passe, corrompido...
        raise ValueError("Não consegui abrir o PDF (pode estar protegido com palavra-passe ou danificado). "
                         "Experimenta exportar o extrato em CSV ou Excel.") from erro


def _ler(conteudo: bytes) -> tuple[pd.DataFrame, dict]:
    try:
        with _abrir(conteudo) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
            if len(texto.strip()) < 20:
                raise ValueError("Este PDF parece ser uma imagem (digitalizado), por isso não tem texto para ler. "
                                 "Exporta o extrato diretamente da app ou do site do banco.")
            por_tabelas = _ler_tabelas(pdf)
            movimentos, info = _ler_palavras(pdf)
    except ValueError:
        raise
    except Exception as erro:  # erros internos do leitor de PDF (protegido, danificado...)
        raise ValueError("Não consegui ler este PDF (pode estar protegido com palavra-passe ou danificado). "
                         "Experimenta exportar o extrato em CSV ou Excel.") from erro

    _completar_anos(movimentos, texto)
    _sinais_pelo_saldo(movimentos, info["saldo_inicial"])
    _sinais_pela_convencao(movimentos)
    por_palavras = pd.DataFrame({
        "data": pd.to_datetime([m.data for m in movimentos]),
        "descricao": [m.descricao for m in movimentos],
        # Sem coluna nem saldo que diga o sinal: assumimos saída (o mais comum num extrato).
        "valor": [m.valor if m.valor is not None else -m.absoluto for m in movimentos],
    }) if movimentos else pd.DataFrame(columns=["data", "descricao", "valor"])
    info["sem_sinal"] = sum(not m.sinal_conhecido for m in movimentos)
    info["pelo_saldo"] = sum(m.origem == "saldo" for m in movimentos)

    def pontos(df):
        if df is None or df.empty:
            return -1
        return len(df) + (len(df) * 0.2 if (df["valor"] > 0).any() and (df["valor"] < 0).any() else 0)

    if pontos(por_tabelas) >= pontos(por_palavras) and por_tabelas is not None:
        info["metodo"] = "tabela"
        resultado = por_tabelas
    else:
        info["metodo"] = "colunas" if info["cabecalho"] else "texto"
        resultado = por_palavras
    if resultado.empty:
        raise ValueError("Não encontrei movimentos neste PDF. Experimenta exportar em CSV ou Excel, "
                         "ou abre o diagnóstico para ver a estrutura do ficheiro.")
    resultado = resultado[resultado["valor"].abs() > 0.004]
    info["movimentos"] = len(resultado)
    return resultado.sort_values("data", kind="stable").reset_index(drop=True), info


def ler_extrato_pdf(conteudo: bytes) -> pd.DataFrame:
    return _ler(conteudo)[0]


def diagnostico_pdf(conteudo: bytes, max_linhas: int = 45) -> dict:
    """Informação para perceber porque é que um PDF foi mal lido — sem dados pessoais."""
    try:
        df, info = _ler(conteudo)
        info["erro"] = ""
        info["entradas"] = int((df["valor"] > 0).sum())
        info["saidas"] = int((df["valor"] < 0).sum())
    except ValueError as erro:
        info = {"erro": str(erro), "metodo": "-", "cabecalho": "", "linhas_com_data": 0, "movimentos": 0}
    with _abrir(conteudo) as pdf:
        texto = "\n".join(p.extract_text(layout=True) or "" for p in pdf.pages[:2])
    linhas = [l.rstrip() for l in texto.splitlines() if l.strip()]
    info["texto"] = "\n".join(anonimizar(l) for l in linhas[:max_linhas])
    return info
