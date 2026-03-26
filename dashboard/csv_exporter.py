import logging
import csv
from datetime import date
from typing import Dict, List, Optional
from models import NormalizedDataset, Developer, TrainingRecord, DeveloperOrgHistory, InvitationBatch, Training
from normalize import get_status

logger = logging.getLogger(__name__)


class CSVExporter:

    def __init__(self, dataset: NormalizedDataset):
        self.dataset = dataset
        self._index_data()

    def _index_data(self):
        self.devs_by_id = {d.id: d for d in self.dataset.developers}
        self.batches_by_id = {b.id: b for b in self.dataset.invitation_batches}
        self.trainings_by_id = {t.id: t for t in self.dataset.trainings}
        self.orgs_by_dev_id = {}
        for org in self.dataset.org_history:
            if org.developer_id not in self.orgs_by_dev_id:
                self.orgs_by_dev_id[org.developer_id] = []
            self.orgs_by_dev_id[org.developer_id].append(org)

    def export_to_file(self, output_file: str, batch_code: Optional[str] = None):
        rows = self._build_rows(batch_code)
        self._write_csv(output_file, rows)
        logger.info(f"Exported {len(rows)} rows to {output_file}")

    def _build_rows(self, batch_code: Optional[str]) -> List[Dict]:
        rows = []
        for record in self.dataset.training_records:
            batch = self.batches_by_id.get(record.invitation_batch_id)
            if not batch:
                continue
            if batch_code and batch.batch_code != batch_code:
                continue
            row = self._build_row(record, batch)
            if row:
                rows.append(row)
        return rows

    def _build_row(self, record: TrainingRecord, batch: InvitationBatch) -> Optional[Dict]:
        dev = self.devs_by_id.get(record.developer_id)
        if not dev:
            return None
        training = self.trainings_by_id.get(batch.training_id)
        if not training:
            return None
        org = self._get_current_org_for_dev(dev.id)
        status = get_status(dev, record, batch)
        return {
            'developer_id': dev.id,
            'email': dev.email,
            'full_name': dev.full_name,
            'is_active': dev.is_active,
            'left_on': dev.left_on.isoformat() if dev.left_on else '',
            'exemption_start': dev.exemption_start.isoformat() if dev.exemption_start else '',
            'exemption_end': dev.exemption_end.isoformat() if dev.exemption_end else '',
            'vp': org.vp if org else '',
            'director': org.director if org else '',
            'manager_email': org.manager_email if org else '',
            'completed': record.completed,
            'completion_date': record.completion_date.isoformat() if record.completion_date else '',
            'attempts': record.attempts,
            'status': status,
            'training_name': training.name,
            'batch_code': batch.batch_code,
            'due_date': batch.due_date.isoformat(),
        }

    def _get_current_org_for_dev(self, dev_id: str) -> Optional[DeveloperOrgHistory]:
        orgs = self.orgs_by_dev_id.get(dev_id, [])
        if not orgs:
            return None
        orgs_sorted = sorted(orgs, key=lambda o: o.effective_from, reverse=True)
        for org in orgs_sorted:
            if org.effective_to is None:
                return org
        return orgs_sorted[0] if orgs_sorted else None

    def _write_csv(self, output_file: str, rows: List[Dict]):
        if not rows:
            logger.warning("No rows to write to CSV")
            return
        fieldnames = self._get_fieldnames()
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _get_fieldnames(self) -> List[str]:
        return [
            'developer_id', 'email', 'full_name', 'is_active', 'left_on',
            'exemption_start', 'exemption_end', 'vp', 'director', 'manager_email',
            'completed', 'completion_date', 'attempts', 'status',
            'training_name', 'batch_code', 'due_date',
        ]
