from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Annotated

from minmodkg.libraries.rdf.rdf_model import P, RDFModel, Subject
from minmodkg.models.kg.base import NS_MO, NS_MR
from minmodkg.typing import IRI, InternalID


@dataclass
class DepositType(RDFModel):
    __subj__ = Subject(type=NS_MO.term("DepositType"), key_ns=NS_MR, key="uri")

    id: Annotated[InternalID, P()]
    name: Annotated[str, P()]
    environment: Annotated[str, P()]
    group: Annotated[str, P()]

    @cached_property
    def uri(self) -> IRI:
        return DepositType.__subj__.key_ns.uristr(self.id)
