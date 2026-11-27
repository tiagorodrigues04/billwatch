"""Erros e estatísticas anónimas para o PostHog, para saber quando a app falha a alguém.

Só funciona na app com servidor (Streamlit Cloud) e só se a chave do projeto estiver configurada
(POSTHOG_PROJECT_TOKEN, numa variável de ambiente ou nos Secrets do Streamlit). Sem chave, ou na
versão do browser (onde o pacote posthog nem existe), não faz nada.

O que é enviado, e o que nunca é:
- Erros: o tipo, a linha do código onde aconteceu e a mensagem passada por anonimizar() (letras
  viram "x", números viram "9"), porque uma mensagem como "could not convert 'NETFLIX 9,99'" pode
  levar um bocado do extrato. Nunca as variáveis do código (estão desligadas).
- Estatísticas: que página se abriu, quantos ficheiros e de que formato, e porque é que um ficheiro
  não foi lido. Nunca descrições, valores, nomes, datas, nem os próprios ficheiros.
- Quem: um código aleatório por sessão, que não fica no browser (sem cookies) e não cria perfis.
  O PostHog não guarda a localização (disable_geoip) e o projeto está na nuvem da UE.

Na página "Como funciona" a pessoa pode desligar o envio para a sessão dela.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

import streamlit as st

from contas.texto import anonimizar

VARIAVEL_CHAVE = "POSTHOG_PROJECT_TOKEN"
VARIAVEL_HOST = "POSTHOG_HOST"
HOST_PADRAO = "https://eu.i.posthog.com"
RAIZ = Path(__file__).resolve().parent.parent

_ID = "_telemetria_id"
_DESLIGADA = "_telemetria_desligada"
_ULTIMA_PAGINA = "_telemetria_pagina"
_log = logging.getLogger("billwatch.telemetria")


def _configuracao(nome: str) -> str | None:
    """Uma variável de ambiente ou, no Streamlit Cloud, um dos Secrets (opcional: pode faltar)."""
    valor = os.environ.get(nome, "").strip()
    if valor:
        return valor
    try:
        return str(st.secrets.get(nome, "")).strip() or None
    except Exception:  # noqa: BLE001  sem ficheiro de secrets (local, testes, browser)
        return None


def limpar_evento(evento: dict) -> dict:
    """Passa as mensagens dos erros por anonimizar() antes de o evento sair da app."""
    for excecao in (evento.get("properties") or {}).get("$exception_list") or []:
        if excecao.get("value"):
            excecao["value"] = anonimizar(str(excecao["value"]))
        for quadro in (excecao.get("stacktrace") or {}).get("frames") or []:
            quadro.pop("vars", None)   # variáveis do código: desligadas, mas nunca se sabe
    return evento


@st.cache_resource(show_spinner=False)
def _cliente():
    """Um cliente por processo. None sem chave, ou sem o pacote posthog (versão do browser)."""
    chave = _configuracao(VARIAVEL_CHAVE)
    if not chave:
        _log.warning("%s variable required by PostHog is missing or un-configured, this causes events to be "
                     "silently missed. This error stops appearing once %s is configured",
                     VARIAVEL_CHAVE, VARIAVEL_CHAVE)
        return None
    try:
        from posthog import Posthog
    except ImportError:
        return None
    return Posthog(
        chave,
        host=_configuracao(VARIAVEL_HOST) or HOST_PADRAO,
        enable_exception_autocapture=True,
        capture_exception_code_variables=False,
        disable_geoip=True,
        before_send=limpar_evento,
        project_root=str(RAIZ),
        in_app_modules=["contas", "ui", "paginas", "app"],
        timeout=3,          # enviar estatísticas nunca pode atrasar a app
        max_retries=1,
    )


def ativa() -> bool:
    """O envio está ligado para esta sessão (há chave e a pessoa não o desligou)."""
    return _cliente() is not None and not st.session_state.get(_DESLIGADA, False)


def disponivel() -> bool:
    """Há para onde enviar (para a página "Como funciona" saber se fala disto)."""
    return _cliente() is not None


def desligar(desligada: bool) -> None:
    st.session_state[_DESLIGADA] = desligada


def _quem() -> str:
    if _ID not in st.session_state:
        st.session_state[_ID] = str(uuid.uuid4())
    return st.session_state[_ID]


def _propriedades(extra: dict) -> dict:
    return {"$process_person_profile": False, **extra}


def registar(evento: str, **propriedades) -> None:
    """Uma estatística anónima. Nunca falha nem atrasa a app."""
    if not ativa():
        return
    try:
        _cliente().capture(evento, distinct_id=_quem(), properties=_propriedades(propriedades))
    except Exception:  # noqa: BLE001
        _log.debug("Não consegui registar %s", evento, exc_info=True)


def registar_erro(erro: BaseException, onde: str, **propriedades) -> None:
    """Um erro (a mensagem é anonimizada em limpar_evento). Nunca falha nem atrasa a app."""
    if not ativa():
        return
    try:
        _cliente().capture_exception(erro, distinct_id=_quem(), properties=_propriedades({"onde": onde,
                                                                                             **propriedades}))
    except Exception:  # noqa: BLE001
        _log.debug("Não consegui registar um erro", exc_info=True)


def uma_vez(chave: str) -> bool:
    """True só da primeira vez nesta sessão (o Streamlit volta a correr tudo a cada clique)."""
    vistas: set = st.session_state.setdefault("_telemetria_vistas", set())
    if chave in vistas:
        return False
    vistas.add(chave)
    return True


def pagina_aberta(titulo: str) -> None:
    """Conta uma página só quando se muda para ela (o Streamlit volta a correr a página a cada clique)."""
    if st.session_state.get(_ULTIMA_PAGINA) == titulo:
        return
    st.session_state[_ULTIMA_PAGINA] = titulo
    registar("pagina_aberta", pagina=titulo)


def formato(nome: str) -> str:
    """'Extrato Março.CSV' -> 'csv' (só a extensão: o nome do ficheiro pode ter dados pessoais)."""
    extensao = Path(nome).suffix.lower().lstrip(".")
    return extensao if extensao in {"csv", "txt", "xlsx", "xls", "pdf"} else "outro"
