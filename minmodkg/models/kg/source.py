from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Optional

from minmodkg.libraries.rdf.rdf_model import P, RDFModel, Subject
from minmodkg.models.kg.base import NS_MO, NS_MR_NO_REL
from minmodkg.typing import IRI, NotEmptyStr

SourceType = Literal["database", "article", "mining-report", "unpublished"]


@dataclass
class Source(RDFModel):
    __subj__ = Subject(type=NS_MO.term("Source"), key_ns=NS_MR_NO_REL, key="uri")

    uri: IRI
    name: Annotated[NotEmptyStr, P()]
    type: Annotated[SourceType, P()]
    created_by: Annotated[IRI, P()]
    description: Annotated[NotEmptyStr, P()]
    score: Annotated[Optional[float], P()]
    connection: Annotated[Optional[NotEmptyStr], P()] = None
