"""Catálogo de comerciantes conhecidos em Portugal.

Cada entrada: palavra-chave a procurar na descrição -> (nome bonito, categoria).
As palavras-chave contam como palavras inteiras e a mais comprida ganha, por isso a ordem
da lista não importa ("GALP ENERGIA" ganha a "GALP", "MEO ENERGIA" ganha a "MEO").
Acrescenta aqui os comerciantes que te aparecerem nos testes com colegas.
"""

from __future__ import annotations

import re
import unicodedata

CATALOGO: list[tuple[str, str, str]] = [
    # Streaming e entretenimento
    ("NETFLIX", "Netflix", "Streaming"),
    ("SPOTIFY", "Spotify", "Streaming"),
    ("DISNEY", "Disney+", "Streaming"),
    ("HBO", "HBO Max", "Streaming"),
    ("MAX.COM", "HBO Max", "Streaming"),
    ("PRIMEVIDEO", "Prime Video", "Streaming"),
    ("PRIME VIDEO", "Prime Video", "Streaming"),
    ("AMAZON PRIME", "Amazon Prime", "Streaming"),
    ("AMZN PRIME", "Amazon Prime", "Streaming"),
    ("YOUTUBE", "YouTube Premium", "Streaming"),
    ("DAZN", "DAZN", "Streaming"),
    ("SPORT TV", "Sport TV", "Streaming"),
    ("SPORTTV", "Sport TV", "Streaming"),
    ("ELEVEN SPORTS", "Eleven", "Streaming"),
    ("ELEVENSPORTS", "Eleven", "Streaming"),
    ("TWITCH", "Twitch", "Streaming"),
    ("DEEZER", "Deezer", "Streaming"),
    ("APPLE.COM", "Apple (iCloud/App Store)", "Software e nuvem"),
    ("ICLOUD", "iCloud", "Software e nuvem"),
    ("GOOGLE ONE", "Google One", "Software e nuvem"),
    ("GOOGLE STORAGE", "Google One", "Software e nuvem"),
    ("MICROSOFT", "Microsoft 365", "Software e nuvem"),
    ("ADOBE", "Adobe", "Software e nuvem"),
    ("OPENAI", "ChatGPT", "Software e nuvem"),
    ("CHATGPT", "ChatGPT", "Software e nuvem"),
    ("ANTHROPIC", "Claude", "Software e nuvem"),
    ("CLAUDE.AI", "Claude", "Software e nuvem"),
    ("DROPBOX", "Dropbox", "Software e nuvem"),
    ("CANVA", "Canva", "Software e nuvem"),
    ("DUOLINGO", "Duolingo", "Software e nuvem"),
    ("PLAYSTATION", "PlayStation Plus", "Jogos"),
    ("SONY INTERACTIVE", "PlayStation Plus", "Jogos"),
    ("XBOX", "Xbox Game Pass", "Jogos"),
    ("NINTENDO", "Nintendo", "Jogos"),
    # Telecomunicações
    ("MEO", "MEO", "Telecomunicações"),
    ("NOS COMUNICA", "NOS", "Telecomunicações"),
    ("NOS ", "NOS", "Telecomunicações"),
    ("VODAFONE", "Vodafone", "Telecomunicações"),
    ("DIGI", "DIGI", "Telecomunicações"),
    ("NOWO", "NOWO", "Telecomunicações"),
    ("UZO", "UZO", "Telecomunicações"),
    ("WOO", "WOO", "Telecomunicações"),
    # Energia e água
    ("EDP", "EDP", "Energia"),
    ("ENDESA", "Endesa", "Energia"),
    ("GALP ENERGIA", "Galp", "Energia"),
    ("GALP POWER", "Galp", "Energia"),
    ("GALP GAS", "Galp", "Energia"),
    ("GOLDENERGY", "Goldenergy", "Energia"),
    ("IBERDROLA", "Iberdrola", "Energia"),
    ("PLENITUDE", "Plenitude", "Energia"),
    ("REPSOL ELECTRICIDAD", "Repsol", "Energia"),
    ("REPSOL ELETRICIDADE", "Repsol", "Energia"),
    ("REPSOL LUZ", "Repsol", "Energia"),
    ("REPSOL ENERGIA", "Repsol", "Energia"),
    ("MEO ENERGIA", "MEO Energia", "Energia"),
    ("SU ELETRICIDADE", "SU Eletricidade", "Energia"),
    ("COOPERNICO", "Coopérnico", "Energia"),
    ("AGUAS DO", "Água", "Energia"),
    ("AGUAS DE", "Água", "Energia"),
    ("AGUAS DA", "Água", "Energia"),
    ("EPAL", "Água (EPAL)", "Energia"),
    ("INDAQUA", "Água (Indaqua)", "Energia"),
    ("SMAS", "Água (SMAS)", "Energia"),
    # Ginásios
    ("FITNESS HUT", "Fitness Hut", "Ginásio"),
    ("SOLINCA", "Solinca", "Ginásio"),
    ("GOLDS GYM", "Gold's Gym", "Ginásio"),
    ("HOLMES PLACE", "Holmes Place", "Ginásio"),
    ("FITNESSUP", "FitnessUp", "Ginásio"),
    ("GINASIO", "Ginásio", "Ginásio"),
    ("GYM", "Ginásio", "Ginásio"),
    # Seguros
    ("FIDELIDADE", "Fidelidade", "Seguros"),
    ("TRANQUILIDADE", "Tranquilidade", "Seguros"),
    ("GENERALI", "Generali", "Seguros"),
    ("ALLIANZ", "Allianz", "Seguros"),
    ("AGEAS", "Ageas", "Seguros"),
    ("OK TELESEGUROS", "OK! Teleseguros", "Seguros"),
    ("LOGO SEGUROS", "Logo", "Seguros"),
    ("ZURICH", "Zurich", "Seguros"),
    ("MEDIS", "Médis", "Seguros"),
    ("MULTICARE", "Multicare", "Seguros"),
    ("SEGURO", "Seguro", "Seguros"),
    # Casa
    ("RENDA", "Renda", "Casa"),
    ("CONDOMINIO", "Condomínio", "Casa"),
    ("PROPINA", "Propinas", "Educação"),
    # Poupança e investimento (não contam como custos)
    ("POCKET", "Cofre / poupança", "Poupança e investimento"),
    ("COFRE", "Cofre / poupança", "Poupança e investimento"),
    ("SAVINGS", "Cofre / poupança", "Poupança e investimento"),
    ("VAULT", "Cofre / poupança", "Poupança e investimento"),
    ("POUPANCA", "Poupança", "Poupança e investimento"),
    ("MEALHEIRO", "Mealheiro", "Poupança e investimento"),
    ("ARREDONDAMENTO", "Arredondamentos", "Poupança e investimento"),
    ("ROUND-UP", "Arredondamentos", "Poupança e investimento"),
    ("BITCOIN", "Cripto (BTC)", "Poupança e investimento"),
    ("BTC", "Cripto (BTC)", "Poupança e investimento"),
    ("ETHEREUM", "Cripto (ETH)", "Poupança e investimento"),
    ("ETH", "Cripto (ETH)", "Poupança e investimento"),
    ("CRIPTO", "Cripto", "Poupança e investimento"),
    ("CRYPTO", "Cripto", "Poupança e investimento"),
    ("BINANCE", "Binance", "Poupança e investimento"),
    ("COINBASE", "Coinbase", "Poupança e investimento"),
    ("KRAKEN", "Kraken", "Poupança e investimento"),
    ("TRADING 212", "Trading 212", "Poupança e investimento"),
    ("TRADING212", "Trading 212", "Poupança e investimento"),
    ("XTB", "XTB", "Poupança e investimento"),
    ("DEGIRO", "DEGIRO", "Poupança e investimento"),
    ("ETORO", "eToro", "Poupança e investimento"),
    ("AFORRO", "Certificados de Aforro", "Poupança e investimento"),
    ("PPR", "PPR", "Poupança e investimento"),
    # Mobilidade e entregas com subscrição
    ("UBER ONE", "Uber One", "Mobilidade e entregas"),
    ("GLOVO PRIME", "Glovo Prime", "Mobilidade e entregas"),
    ("BOLT PLUS", "Bolt Plus", "Mobilidade e entregas"),
    ("VIA VERDE", "Via Verde", "Mobilidade e entregas"),
]

# Categorias cujo valor muda naturalmente de mês para mês (consumos).
CATEGORIAS_VARIAVEIS = {"Energia"}
# Recorrentes que não são custos (dinheiro que continua a ser teu).
CATEGORIAS_POUPANCA = {"Poupança e investimento"}


# Nomes que contêm uma palavra-chave do catálogo mas NÃO são contas fixas.
# Ganham ao catálogo porque são mais compridos (procura-se sempre a chave mais longa primeiro).
# Se o pagamento for um débito direto, usa-se o valor do dicionário (a Galp não cobra
# combustível por débito direto, por isso um "SDD GALP" é a conta da luz/gás).
NAO_SUBSCRICAO: dict[str, tuple[str, str] | None] = {
    "GALP": ("Galp", "Energia"),      # abastecer combustível (a luz vem como "GALP ENERGIA"/"GALP POWER")
    "REPSOL": ("Repsol", "Energia"),  # idem
    "GYM SHARK": None, "GYMSHARK": None,   # loja de roupa desportiva, não é ginásio
    "DISNEYLAND": None, "DISNEY STORE": None,
    "GOOGLE PLAY": None,  # compras de apps e jogos (subscrições vêm como GOOGLE *YOUTUBE, GOOGLE ONE...)
}
_DEBITO_DIRETO = re.compile(r" (SDD|DD|DEB DIRE?C?TO|DEBITO DIRE?C?TO|COBRANCA|DIRECT DEBIT) ")

# Palavras genéricas que, numa transferência para uma pessoa (MB WAY, "TRF PARA ..."),
# podem ser o apelido de alguém: "MB WAY PARA JOAO SEGURO" não é um seguro.
GENERICAS = {"SEGURO", "RENDA", "CONDOMINIO", "PROPINA", "GINASIO", "GYM", "POUPANCA", "COFRE"}
_TRANSFERENCIA_PESSOA = re.compile(r" (MB ?WAY|MBWAY|PARA|P) ")

# Chaves com 6+ letras podem ser o início de uma palavra ("YOUTUBE" em "YOUTUBEPREMIUM");
# as mais curtas têm de ser a palavra inteira ("MEO" não conta em "HOMEOPATIA").
_MIN_PREFIXO = 6


def _limpar(texto: str) -> str:
    """Maiúsculas, sem acentos, pontuação vira espaço: ' NETFLIX COM 866 579 '."""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).upper()
    return " " + " ".join(re.sub(r"[^A-Z0-9]+", " ", texto).split()) + " "


def _entradas():
    entradas = [(_limpar(chave).strip(), nome, categoria) for chave, nome, categoria in CATALOGO]
    entradas += [(_limpar(chave).strip(), None, se_dd) for chave, se_dd in NAO_SUBSCRICAO.items()]
    # Procura primeiro as palavras-chave mais compridas (mais específicas).
    return sorted(entradas, key=lambda e: -len(e[0]))


_ENTRADAS = _entradas()


def _aparece(chave: str, texto: str) -> bool:
    if f" {chave} " in texto:
        return True
    return len(chave) >= _MIN_PREFIXO and " " not in chave and f" {chave}" in texto


def identificar(descricao: str) -> tuple[str, str] | None:
    """Devolve (nome, categoria) se a descrição corresponder a um comerciante conhecido."""
    texto = _limpar(descricao)
    para_pessoa = bool(_TRANSFERENCIA_PESSOA.search(texto))
    for chave, nome, categoria in _ENTRADAS:
        if para_pessoa and chave in GENERICAS:
            continue
        if _aparece(chave, texto):
            if nome:
                return nome, categoria
            # Entrada de NAO_SUBSCRICAO: só conta se for um débito direto e houver alternativa.
            return categoria if categoria and _DEBITO_DIRETO.search(texto) else None
    return None
