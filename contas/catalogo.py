"""Catálogo de comerciantes conhecidos em Portugal.

Cada entrada: palavra-chave a procurar na descrição -> (nome bonito, categoria).
A ordem importa: entradas mais específicas primeiro (ex.: "YOUTUBE" antes de "GOOGLE").
Acrescenta aqui os comerciantes que te aparecerem nos testes com colegas.
"""

from __future__ import annotations

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
    ("ELEVEN", "Eleven", "Streaming"),
    ("TWITCH", "Twitch", "Streaming"),
    ("DEEZER", "Deezer", "Streaming"),
    ("APPLE.COM", "Apple (iCloud/App Store)", "Software e nuvem"),
    ("ICLOUD", "iCloud", "Software e nuvem"),
    ("GOOGLE ONE", "Google One", "Software e nuvem"),
    ("GOOGLE", "Google", "Software e nuvem"),
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
    ("STEAM", "Steam", "Jogos"),
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
    ("GALP", "Galp", "Energia"),
    ("GOLDENERGY", "Goldenergy", "Energia"),
    ("IBERDROLA", "Iberdrola", "Energia"),
    ("PLENITUDE", "Plenitude", "Energia"),
    ("REPSOL", "Repsol", "Energia"),
    ("MEO ENERGIA", "MEO Energia", "Energia"),
    ("SU ELETRICIDADE", "SU Eletricidade", "Energia"),
    ("COOPERNICO", "Coopérnico", "Energia"),
    ("AGUAS", "Água", "Energia"),
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


def _limpar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c)).upper()
    return " " + " ".join(texto.replace("!", " ").split()) + " "


def identificar(descricao: str) -> tuple[str, str] | None:
    """Devolve (nome, categoria) se a descrição corresponder a um comerciante conhecido."""
    texto = _limpar(descricao)
    # Procura primeiro as palavras-chave mais compridas (mais específicas).
    for chave, nome, categoria in sorted(CATALOGO, key=lambda e: -len(e[0])):
        alvo = chave.upper()
        # Palavras-chave curtas (MEO, NOS, EDP...) têm de aparecer como palavra inteira.
        if len(alvo.strip()) <= 4:
            if f" {alvo.strip()} " in texto.replace(".", " ").replace("*", " "):
                return nome, categoria
        elif alvo in texto:
            return nome, categoria
    return None
