from __future__ import annotations

from pathlib import Path
from typing import Mapping, NotRequired, TypedDict

import serde.json
from libactor.cache import cache
from minmodkg.misc.rdf_store import norm_literal
from minmodkg.models_v2.kg.base import MINMOD_NS
from minmodkg.models_v2.kgrel.commodity import Commodity
from rdflib import RDF, RDFS, Graph, URIRef

from statickg.helper import FileSqliteBackend
from statickg.models.etl import ETLOutput
from statickg.models.file_and_path import InputFile, RelPath
from statickg.models.repository import Repository
from statickg.services.interface import BaseFileService, BaseService


class KGRelEntityETLServiceConstructArgs(TypedDict):
    parallel: NotRequired[bool]


class KGRelEntityETLServiceInvokeArgs(TypedDict):
    predefined_entity_dir: RelPath
    output: RelPath


class KGRelEntityETLService(BaseFileService[KGRelEntityETLServiceConstructArgs]):
    def __init__(
        self,
        name: str,
        workdir: Path,
        args: KGRelEntityETLServiceConstructArgs,
        services: Mapping[str, BaseService],
    ):
        super().__init__(name, workdir, args, services)
        self.parallel = args.get("parallel", True)

    def forward(
        self, repo: Repository, args: KGRelEntityETLServiceInvokeArgs, output: ETLOutput
    ):
        predefined_entity_dir = args["predefined_entity_dir"]
        outdir = args["output"]

        outfiles = set()

        outfiles.add(
            TransformFn.exec(
                self.workdir,
                infile=InputFile.from_relpath(predefined_entity_dir / "commodity.ttl"),
                outdir=outdir.get_path(),
            )
        )

        self.remove_unknown_files(outfiles, outdir.get_path())


class TransformFn:
    """Transform RDF data to Relational data"""

    instances = {}

    def __init__(self, workdir: Path):
        self.workdir = workdir

    @staticmethod
    def get_instance(workdir: Path) -> TransformFn:
        if workdir not in TransformFn.instances:
            TransformFn.instances[workdir] = TransformFn(workdir)
        return TransformFn.instances[workdir]

    @classmethod
    def exec(cls, workdir: Path, **kwargs) -> Path:
        return cls.get_instance(workdir).invoke(**kwargs)

    @cache(
        backend=FileSqliteBackend.factory(filename="transform-v105.sqlite"),
        cache_ser_args={
            "infile": lambda x: x.get_ident(),
        },
    )
    def invoke(self, infile: InputFile, outdir: Path) -> Path:
        g = Graph()
        mr = MINMOD_NS.mr
        g.parse(infile.path, format="ttl")
        if infile.path.name == "commodity.ttl":
            is_critical_commodity = MINMOD_NS.mo.uri("is_critical_commodity")

            records = []
            for subj in g.subjects(RDF.type, MINMOD_NS.mo.uri("Commodity")):
                assert isinstance(subj, URIRef)
                r = Commodity(
                    id=mr.id(subj),
                    name=norm_literal(next(g.objects(subj, RDFS.label))),
                    is_critical=norm_literal(
                        next(g.objects(subj, is_critical_commodity))
                    ),
                )
                records.append(r.to_dict())

            outdir.mkdir(parents=True, exist_ok=True)
            outfile = outdir / "commodity.json"
            serde.json.ser({"Commodity": records}, outfile)
            return outfile

        raise NotImplementedError()
