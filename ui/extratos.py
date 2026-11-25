"""Os extratos carregados, partilhados entre as páginas.

O carregador de ficheiros está na página Contas fixas. Quando se muda de página, o Streamlit
esquece o que um widget tinha, por isso os ficheiros são guardados aqui, na sessão: quem vai
ver o Supermercado ou a Luz e volta não tem de os carregar outra vez. Ficam só na sessão,
tal como antes.

A página Contas fixas também publica aqui o extrato já lido (com as escolhas de colunas e os
sinais trocados, se for o caso), e é esse que a página Supermercado usa.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

CARREGADOR = "extratos"             # a chave do st.file_uploader da página Contas fixas
_GUARDADOS = "_extratos_guardados"
_PUBLICADO = "_extrato_publicado"


@dataclass(frozen=True)
class FicheiroGuardado:
    """Um ficheiro carregado, guardado na sessão. Tem o que a leitura usa de um UploadedFile."""
    name: str
    size: int
    file_id: str
    dados: bytes

    def getvalue(self) -> bytes:
        return self.dados


def guardar_ficheiros() -> None:
    """Chamado quando o carregador muda (ficheiros novos ou tirados), e só nessa altura.

    Ao voltar de outra página o carregador aparece vazio sem ter mudado, e os ficheiros guardados
    continuam a valer; se for a pessoa a tirá-los, ficam também tirados daqui.
    """
    st.session_state[_GUARDADOS] = [FicheiroGuardado(f.name, f.size, f.file_id, f.getvalue())
                                    for f in st.session_state.get(CARREGADOR) or []]


def ficheiros_guardados() -> list[FicheiroGuardado]:
    return st.session_state.get(_GUARDADOS, [])


def esquecer_ficheiros() -> None:
    st.session_state[_GUARDADOS] = []


@dataclass(frozen=True)
class ExtratoPublicado:
    extrato: pd.DataFrame | None      # None: sem ficheiros e sem o exemplo
    exemplo: bool
    ficheiros: int


def publicar(extrato: pd.DataFrame | None, exemplo: bool, ficheiros: int) -> None:
    st.session_state[_PUBLICADO] = ExtratoPublicado(extrato, exemplo, ficheiros)


def extrato_publicado() -> ExtratoPublicado | None:
    """O extrato que está a ser analisado em Contas fixas, ou None se essa página ainda não abriu."""
    return st.session_state.get(_PUBLICADO)
