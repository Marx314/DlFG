import logging
import uuid
from datetime import date
from typing import List, Dict, Tuple, Optional
from models import (
    Training,
    InvitationBatch,
    Developer,
    DeveloperOrgHistory,
    TrainingRecord,
    TrainingStatus,
    NormalizedDataset,
)
from scw import SCWClient

logger = logging.getLogger(__name__)


def get_status(
    developer: Developer,
    training_record: Optional[TrainingRecord],
    batch: Optional[InvitationBatch]
) -> str:
    if not developer.is_active:
        return TrainingStatus.DEPARTED.value

    if developer.exemption_start and not developer.exemption_end:
        return TrainingStatus.EXEMPT.value

    if training_record and training_record.completed:
        return TrainingStatus.COMPLETED.value

    if batch and batch.due_date < date.today():
        return TrainingStatus.OVERDUE.value

    return TrainingStatus.PENDING.value


class Normalizer:

    def __init__(self, existing_dataset: Optional[NormalizedDataset] = None):
        self.existing_dataset = existing_dataset
        self.existing_developers = {}
        self.existing_org_history = {}

        if existing_dataset:
            for dev in existing_dataset.developers:
                self.existing_developers[dev.email.lower()] = dev

            for org in existing_dataset.org_history:
                if org.developer_id not in self.existing_org_history:
                    self.existing_org_history[org.developer_id] = []
                self.existing_org_history[org.developer_id].append(org)

    def normalize(
        self,
        entra_users: List[Dict],
        manager_chains: Dict[str, Tuple],
        scw_tags: List[Dict],
        scw_users_per_tag: Dict[str, List[Dict]],
    ) -> NormalizedDataset:
        logger.info("Starting data normalization...")

        developers_list, org_history_list = self._build_developers_and_org_history(
            entra_users, manager_chains
        )

        trainings_list, invitation_batches_list = self._build_trainings_and_batches(scw_tags)

        training_records_list = self._build_training_records(
            developers_list, invitation_batches_list, scw_users_per_tag
        )

        logger.info(f"Normalized dataset: {len(developers_list)} developers, "
                    f"{len(training_records_list)} training records, "
                    f"{len(org_history_list)} org history rows")

        return NormalizedDataset(
            trainings=trainings_list,
            invitation_batches=invitation_batches_list,
            developers=developers_list,
            org_history=org_history_list,
            training_records=training_records_list,
        )

    def _build_developers_and_org_history(
        self,
        entra_users: List[Dict],
        manager_chains: Dict[str, Tuple],
    ) -> Tuple[List[Developer], List[DeveloperOrgHistory]]:
        developers = []
        org_history = []
        for user in entra_users:
            dev = self._create_developer(user)
            developers.append(dev)
            org_hist = self._create_org_history(user.get('id'), user.get('mail', '').lower(), manager_chains)
            org_history.append(org_hist)
        return developers, org_history

    def _create_developer(self, user: Dict) -> Developer:
        user_id = user.get('id')
        email = user.get('mail', '').lower()
        full_name = user.get('displayName', 'Unknown')
        is_active = user.get('accountEnabled', False)
        left_on = self._parse_left_on_date(user) if not is_active else None
        return Developer(id=user_id, email=email, full_name=full_name, is_active=is_active, left_on=left_on)

    def _parse_left_on_date(self, user: Dict) -> Optional[date]:
        offboarded_str = user.get('offboardedDateTime')
        if offboarded_str:
            try:
                return self._parse_date(offboarded_str)
            except:
                pass
        return None

    def _create_org_history(self, user_id: str, email: str, manager_chains: Dict[str, Tuple]) -> DeveloperOrgHistory:
        chain = manager_chains.get(user_id, (None, None, None, None))
        manager_email, director, principal_director, vp = chain
        self._close_previous_org_record_if_changed(user_id, manager_email, director, principal_director, vp)
        logger.debug(f"Developer: {email} → {vp or director or manager_email or 'No manager'}")
        return DeveloperOrgHistory(
            id=str(uuid.uuid4()),
            developer_id=user_id,
            manager_email=manager_email,
            director=director,
            principal_director=principal_director,
            vp=vp,
            effective_from=date.today(),
            effective_to=None,
        )

    def _close_previous_org_record_if_changed(self, user_id: str, manager_email: Optional[str], director: Optional[str], principal_director: Optional[str], vp: Optional[str]):
        if self._org_position_changed(user_id, '', manager_email, director, principal_director, vp):
            if user_id in self.existing_org_history:
                prev_rows = self.existing_org_history[user_id]
                if prev_rows and prev_rows[-1].effective_to is None:
                    prev_rows[-1].effective_to = date.today()

    def _org_position_changed(
        self,
        user_id: str,
        email: str,
        manager_email: Optional[str],
        director: Optional[str],
        principal_director: Optional[str],
        vp: Optional[str],
    ) -> bool:
        if user_id not in self.existing_org_history:
            return True

        prev_rows = self.existing_org_history[user_id]
        if not prev_rows:
            return True

        last_row = prev_rows[-1]

        return (
            last_row.manager_email != manager_email
            or last_row.director != director
            or last_row.principal_director != principal_director
            or last_row.vp != vp
        )

    def _build_trainings_and_batches(
        self,
        scw_tags: List[Dict],
    ) -> Tuple[List[Training], List[InvitationBatch]]:
        trainings = {}
        invitation_batches = []

        for tag in scw_tags:
            tag_name = tag.get('name', '')
            tag_id = tag.get('id')

            if not SCWClient.is_valid_batch_tag(tag_name):
                logger.debug(f"Skipping tag (invalid format): {tag_name}")
                continue

            parsed = SCWClient.parse_batch_tag(tag_name)
            if not parsed:
                continue

            year, month = parsed
            training_year = year

            if training_year not in trainings:
                trainings[training_year] = Training(
                    id=str(uuid.uuid4()),
                    name=f"Security Training {training_year}",
                    training_year=training_year,
                    type="secure_code_warrior",
                )

            batch = InvitationBatch(
                id=tag_id,
                training_id=trainings[training_year].id,
                batch_code=tag_name,
                invited_on=SCWClient.get_batch_invited_date(tag_name),
                due_date=SCWClient.calculate_due_date(tag_name),
                notes=None,
            )
            invitation_batches.append(batch)

        return list(trainings.values()), invitation_batches

    def _build_training_records(
        self,
        developers_list: List[Developer],
        invitation_batches_list: List[InvitationBatch],
        scw_users_per_tag: Dict[str, List[Dict]],
    ) -> List[TrainingRecord]:
        developers_by_email = {dev.email: dev for dev in developers_list}
        batches_by_code = {batch.batch_code: batch for batch in invitation_batches_list}
        records = []
        for batch_code, scw_users in scw_users_per_tag.items():
            batch = batches_by_code.get(batch_code)
            if not batch:
                logger.warning(f"Batch {batch_code} not found in invitation_batches")
                continue
            for scw_user in scw_users:
                record = self._create_training_record(scw_user, batch, developers_by_email)
                if record:
                    records.append(record)
        return records

    def _create_training_record(self, scw_user: Dict, batch: InvitationBatch, developers_by_email: Dict) -> Optional[TrainingRecord]:
        scw_email = scw_user.get('email', '').lower()
        developer = developers_by_email.get(scw_email)
        if not developer:
            logger.warning(f"SCW user {scw_email} not found in Entra ID")
            return None
        completion_date = self._parse_scw_completion_date(scw_user, scw_email)
        return TrainingRecord(
            id=str(uuid.uuid4()),
            developer_id=developer.id,
            invitation_batch_id=batch.id,
            completed=scw_user.get('completed', False),
            completion_date=completion_date,
            attempts=scw_user.get('attempts', 0),
            last_reminder_sent=None,
            reminders_sent_count=0,
        )

    def _parse_scw_completion_date(self, scw_user: Dict, email: str) -> Optional[date]:
        completion_date_str = scw_user.get('completion_date')
        if not completion_date_str:
            return None
        try:
            return self._parse_date(completion_date_str)
        except:
            logger.warning(f"Could not parse completion_date for {email}: {completion_date_str}")
            return None

    @staticmethod
    def _parse_date(date_str: str) -> date:
        if 'T' in date_str:
            return date.fromisoformat(date_str.split('T')[0])
        else:
            return date.fromisoformat(date_str)
