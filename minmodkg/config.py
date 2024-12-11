from __future__ import annotations

import os
from pathlib import Path

import serde.yaml
from minmodkg.misc.rdf_store import (
    BaseRDFModel,
    BaseRDFQueryBuilder,
    Namespace,
    RDFMetadata,
    RDFStore,
)

if "CFG_FILE" not in os.environ:
    CFG_FILE = Path(__file__).parent.parent / "config.yml"
else:
    CFG_FILE = Path(os.environ["CFG_FILE"])
assert CFG_FILE.exists(), f"Config file {CFG_FILE} does not exist"
cfg = serde.yaml.deser(CFG_FILE)

# for minmod KG
SPARQL_QUERY_ENDPOINT = cfg["triplestore"]["query"]
SPARQL_UPDATE_ENDPOINT = cfg["triplestore"]["update"]
MINMOD_NS_CFG = cfg["namespace"]

# for API prefixes
API_PREFIX = cfg["api_prefix"]
LOD_PREFIX = cfg["lod_prefix"]

while API_PREFIX.endswith("/"):
    API_PREFIX = API_PREFIX[:-1]

while LOD_PREFIX.endswith("/"):
    LOD_PREFIX = LOD_PREFIX[:-1]

# for databases
DBFILE = Path(cfg["dbfile"])
DBFILE.parent.mkdir(parents=True, exist_ok=True)

# for login/security
SECRET_KEY = cfg["secret_key"]
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 3  # 3 days


if __name__ == "__main__":
    import typer

    app = typer.Typer(pretty_exceptions_short=True, pretty_exceptions_enable=False)

    @app.command()
    def update_config(key: str, value: str):
        cfg = serde.yaml.deser(CFG_FILE)
        cfg[key] = value
        serde.yaml.ser(cfg, CFG_FILE)

    app()
