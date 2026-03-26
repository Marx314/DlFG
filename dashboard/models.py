
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional, List, Dict
from enum import Enum
import json


class TrainingStatus(str, Enum):
    DEPARTED = "departed"
    EXEMPT = "exempt"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    PENDING = "pending"


@dataclass
class Training:
    id: str
    name: str
    training_year: int
    type: str

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Training':
        return cls(
            id=data['id'],
            name=data['name'],
            training_year=data['training_year'],
            type=data['type'],
        )


@dataclass
class InvitationBatch:
    id: str
    training_id: str
    batch_code: str
    invited_on: date
    due_date: date
    notes: Optional[str] = None

    def to_dict(self) -> Dict:
        data = asdict(self)
        data['invited_on'] = self.invited_on.isoformat()
        data['due_date'] = self.due_date.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'InvitationBatch':
        return cls(
            id=data['id'],
            training_id=data['training_id'],
            batch_code=data['batch_code'],
            invited_on=date.fromisoformat(data['invited_on']),
            due_date=date.fromisoformat(data['due_date']),
            notes=data.get('notes'),
        )


@dataclass
class Developer:
    id: str
    email: str
    full_name: str
    is_active: bool
    left_on: Optional[date] = None
    exemption_start: Optional[date] = None
    exemption_end: Optional[date] = None
    exemption_reason: Optional[str] = None

    def to_dict(self) -> Dict:
        data = asdict(self)
        if self.left_on:
            data['left_on'] = self.left_on.isoformat()
        if self.exemption_start:
            data['exemption_start'] = self.exemption_start.isoformat()
        if self.exemption_end:
            data['exemption_end'] = self.exemption_end.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'Developer':
        return cls(
            id=data['id'],
            email=data['email'],
            full_name=data['full_name'],
            is_active=data['is_active'],
            left_on=date.fromisoformat(data['left_on']) if data.get('left_on') else None,
            exemption_start=date.fromisoformat(data['exemption_start']) if data.get('exemption_start') else None,
            exemption_end=date.fromisoformat(data['exemption_end']) if data.get('exemption_end') else None,
            exemption_reason=data.get('exemption_reason'),
        )


@dataclass
class DeveloperOrgHistory:
    id: str
    developer_id: str
    manager_email: Optional[str] = None
    director: Optional[str] = None
    principal_director: Optional[str] = None
    vp: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

    def to_dict(self) -> Dict:
        data = asdict(self)
        if self.effective_from:
            data['effective_from'] = self.effective_from.isoformat()
        if self.effective_to:
            data['effective_to'] = self.effective_to.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'DeveloperOrgHistory':
        return cls(
            id=data['id'],
            developer_id=data['developer_id'],
            manager_email=data.get('manager_email'),
            director=data.get('director'),
            principal_director=data.get('principal_director'),
            vp=data.get('vp'),
            effective_from=date.fromisoformat(data['effective_from']) if data.get('effective_from') else None,
            effective_to=date.fromisoformat(data['effective_to']) if data.get('effective_to') else None,
        )


@dataclass
class TrainingRecord:
    id: str
    developer_id: str
    invitation_batch_id: str
    completed: bool
    completion_date: Optional[date] = None
    attempts: int = 0
    last_reminder_sent: Optional[date] = None
    reminders_sent_count: int = 0

    def to_dict(self) -> Dict:
        data = asdict(self)
        if self.completion_date:
            data['completion_date'] = self.completion_date.isoformat()
        if self.last_reminder_sent:
            data['last_reminder_sent'] = self.last_reminder_sent.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'TrainingRecord':
        return cls(
            id=data['id'],
            developer_id=data['developer_id'],
            invitation_batch_id=data['invitation_batch_id'],
            completed=data['completed'],
            completion_date=date.fromisoformat(data['completion_date']) if data.get('completion_date') else None,
            attempts=data.get('attempts', 0),
            last_reminder_sent=date.fromisoformat(data['last_reminder_sent']) if data.get('last_reminder_sent') else None,
            reminders_sent_count=data.get('reminders_sent_count', 0),
        )


@dataclass
class NormalizedDataset:
    trainings: List[Training] = field(default_factory=list)
    invitation_batches: List[InvitationBatch] = field(default_factory=list)
    developers: List[Developer] = field(default_factory=list)
    org_history: List[DeveloperOrgHistory] = field(default_factory=list)
    training_records: List[TrainingRecord] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'trainings': [t.to_dict() for t in self.trainings],
            'invitation_batches': [b.to_dict() for b in self.invitation_batches],
            'developers': [d.to_dict() for d in self.developers],
            'org_history': [o.to_dict() for o in self.org_history],
            'training_records': [r.to_dict() for r in self.training_records],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict) -> 'NormalizedDataset':
        return cls(
            trainings=[Training.from_dict(t) for t in data.get('trainings', [])],
            invitation_batches=[InvitationBatch.from_dict(b) for b in data.get('invitation_batches', [])],
            developers=[Developer.from_dict(d) for d in data.get('developers', [])],
            org_history=[DeveloperOrgHistory.from_dict(o) for o in data.get('org_history', [])],
            training_records=[TrainingRecord.from_dict(r) for r in data.get('training_records', [])],
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'NormalizedDataset':
        data = json.loads(json_str)
        return cls.from_dict(data)
