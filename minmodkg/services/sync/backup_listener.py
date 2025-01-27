from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Literal, Sequence

import serde.csv
import serde.json
from minmodkg.etl.mineral_site import COMPRESSION, PartitionFn
from minmodkg.misc.utils import format_nanoseconds
from minmodkg.models.kgrel.data_source import DataSource
from minmodkg.models.kgrel.event import EventLog
from minmodkg.models.kgrel.mineral_site import MineralSiteAndInventory
from minmodkg.models.kgrel.user import get_username
from minmodkg.services.kgrel_entity import EntityService
from minmodkg.services.sync.listener import Listener
from minmodkg.typing import IRI, InternalID

from statickg.models.repository import GitRepository


class BackupListener(Listener):
    def __init__(self, data_repo_dir: Path):
        super().__init__()
        self.data_repo_dir = data_repo_dir

    def handle_begin(self, events: Sequence[EventLog]):
        self.site_journal: dict[tuple, list[tuple[Literal["add", "update"], dict]]] = (
            defaultdict(list)
        )
        self.same_as_journal: dict[
            str, list[tuple[InternalID, InternalID, int, int]]
        ] = defaultdict(list)

    def handle_site_add(self, event: EventLog, site: MineralSiteAndInventory):
        self._upsert_site("add", site)

    def handle_site_update(self, event: EventLog, site: MineralSiteAndInventory):
        self._upsert_site("update", site)

    def handle_same_as_update(
        self,
        event: EventLog,
        user_uri: str,
        groups: list[list[InternalID]],
        diff_groups: dict[InternalID, list[InternalID]],
    ):
        # write the same as links to the journal
        # there will be a single same-as file for all users
        username = get_username(user_uri)
        records = []
        for group in groups:
            for target in group[1:]:
                records.append((group[0], target, event.timestamp, 1))
        for site_id, diff_sites in diff_groups.items():
            for diff_site in diff_sites:
                records.append((site_id, diff_site, event.timestamp, 0))
        self.same_as_journal[username].extend(records)

    def handle_end(self, events: Sequence[EventLog]):
        for (username, source_name, bucket_no), actions in self.site_journal.items():
            outfile = (
                self.data_repo_dir
                / f"data/mineral-sites/{PartitionFn.get_filename(username, source_name, bucket_no)}"
            )
            if outfile.exists():
                sites = serde.json.deser(outfile)
                id2index = {r["record_id"]: i for i, r in enumerate(sites)}
            else:
                sites = []
                id2index = {}

            for action, site in actions:
                if action == "add":
                    sites.append(site)
                    id2index[site["record_id"]] = len(sites) - 1
                else:
                    assert action == "update"
                    sites[id2index[site["record_id"]]] = site

            outfile.parent.mkdir(parents=True, exist_ok=True)
            serde.json.ser(sites, outfile)

        for username, same_as_links in self.same_as_journal.items():
            outfile = (
                self.data_repo_dir / f"data/same-as/{username}/same_as.csv{COMPRESSION}"
            )
            if outfile.exists():
                records = serde.csv.deser(outfile)
                key2idx = {(r[0], r[1]): i for i, r in enumerate(records)}
            else:
                records = []
                key2idx = {}

            delete_indices = set()
            for s, o, ts, is_same in same_as_links:
                key = (s, o)
                if key in key2idx:
                    delete_indices.add(key2idx[key])
                records.append([s, o, str(ts), str(is_same)])
                key2idx[key] = len(records) - 1

            output = [["ms_1", "ms_2", "time_ns", "is_same"]]
            output.extend((r for i, r in enumerate(records) if i not in delete_indices))
            outfile.parent.mkdir(parents=True, exist_ok=True)
            serde.csv.ser(output, outfile)

        if len(events) > 0:
            # after updating the files, we need to commit the changes to the git repo
            GitRepository(self.data_repo_dir).commit_all(
                f"Backup data as of {format_nanoseconds(events[-1].timestamp)}"
            ).push()

    def _upsert_site(
        self, action: Literal["add", "update"], site: MineralSiteAndInventory
    ):
        username = get_username(site.ms.created_by)

        source_id = site.ms.source_id
        lst = source_id.split("::")
        if len(lst) > 1:
            source_id = lst[1]

        data_sources = EntityService.get_instance().get_data_sources()
        if source_id not in data_sources:
            data_sources = EntityService.get_instance().get_data_sources(refresh=True)

        # determine the bucket that we are going to write the data to.
        # (username, data source, bucket number)
        bucket_no = PartitionFn.get_bucket_no(site.ms.record_id)
        key = (username, data_sources[source_id].slug_name, bucket_no)

        self.site_journal[key].append((action, site.ms.to_kg().to_dict()))
