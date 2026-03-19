from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from db.enums import (
    ActionStatus,
    ActionType,
    DeviceType,
    EventType,
    OutcomeType,
    PlanStatus,
    PolicyType,
    RoleType,
    SessionMode,
    SessionStatus,
    SourceType,
)


plan_status_enum = PGEnum(PlanStatus, name="plan_status_enum", create_type=False)
action_status_enum = PGEnum(ActionStatus, name="action_status_enum", create_type=False)
action_type_enum = PGEnum(ActionType, name="action_type_enum", create_type=False)
outcome_type_enum = PGEnum(OutcomeType, name="outcome_type_enum", create_type=False)
session_mode_enum = PGEnum(SessionMode, name="session_mode_enum", create_type=False)
session_status_enum = PGEnum(SessionStatus, name="session_status_enum", create_type=False)
event_type_enum = PGEnum(EventType, name="event_type_enum", create_type=False)
role_type_enum = PGEnum(RoleType, name="role_type_enum", create_type=False)
policy_type_enum = PGEnum(PolicyType, name="policy_type_enum", create_type=False)
device_type_enum = PGEnum(DeviceType, name="device_type_enum", create_type=False)
source_type_enum = PGEnum(SourceType, name="source_type_enum", create_type=False)


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class TimestampMixin(CreatedAtMixin, UpdatedAtMixin):
    pass


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(Text, server_default=text("'UTC'"))

    devices: Mapped[list["Device"]] = relationship(back_populates="user")
    sessions: Mapped[list["Session"]] = relationship(back_populates="user")
    memory_events: Mapped[list["MemoryEvent"]] = relationship(back_populates="user")
    preferences: Mapped[list["UserPreference"]] = relationship(back_populates="user")
    policies: Mapped[list["OperationalPolicy"]] = relationship(back_populates="user")


class Device(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (Index("idx_devices_user_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(device_type_enum, nullable=False)
    hostname: Mapped[str | None] = mapped_column(Text)
    os: Mapped[str | None] = mapped_column(Text)
    local_agent_version: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="devices")
    sessions: Mapped[list["Session"]] = relationship(back_populates="device")
    file_entities: Mapped[list["FileEntity"]] = relationship(back_populates="device")
    folder_entities: Mapped[list["FolderEntity"]] = relationship(back_populates="device")
    memory_events: Mapped[list["MemoryEvent"]] = relationship(back_populates="device")


class Session(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("idx_sessions_user_id", "user_id"),
        Index("idx_sessions_device_id", "device_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id"),
    )
    title: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[SessionMode] = mapped_column(
        session_mode_enum,
        nullable=False,
        server_default=text("'CHAT'"),
    )
    status: Mapped[SessionStatus] = mapped_column(
        session_status_enum,
        nullable=False,
        server_default=text("'ACTIVE'"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="sessions")
    device: Mapped[Device | None] = relationship(back_populates="sessions")
    messages: Mapped[list[SessionMessage]] = relationship(back_populates="session")
    task_state: Mapped[TaskState | None] = relationship(back_populates="session")
    plans: Mapped[list[Plan]] = relationship(back_populates="session")
    memory_events: Mapped[list[MemoryEvent]] = relationship(back_populates="session")


class SessionMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "session_messages"
    __table_args__ = (Index("idx_session_messages_session_id", "session_id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
        nullable=False,
    )
    role: Mapped[RoleType] = mapped_column(role_type_enum, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(Text)
    tool_call_id: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    session: Mapped[Session] = relationship(back_populates="messages")


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (
        Index("idx_plans_session_id", "session_id"),
        Index("idx_plans_status", "status"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
        nullable=False,
    )
    plan_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'FILE_REORGANIZATION'"),
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rationale_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[PlanStatus] = mapped_column(
        plan_status_enum,
        nullable=False,
        server_default=text("'DRAFT'"),
    )

    session: Mapped[Session] = relationship(back_populates="plans")
    actions: Mapped[list[PlanAction]] = relationship(back_populates="plan")
    task_states: Mapped[list[TaskState]] = relationship(back_populates="active_plan")


class TaskState(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "task_state"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_task_state_session_id"),
        Index("idx_task_state_active_plan_id", "active_plan_id"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
        nullable=False,
    )
    goal: Mapped[str | None] = mapped_column(Text)
    current_step: Mapped[str | None] = mapped_column(Text)
    active_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id"),
    )
    active_entities_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pending_action_ids_json: Mapped[list[str] | None] = mapped_column(JSONB)
    scratchpad_summary: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    session: Mapped[Session] = relationship(back_populates="task_state")
    active_plan: Mapped[Plan | None] = relationship(back_populates="task_states")


class FileEntity(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "file_entities"
    __table_args__ = (
        UniqueConstraint("device_id", "canonical_path", name="uq_file_entities_device_path"),
        Index("idx_file_entities_device_id", "device_id"),
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id"),
        nullable=False,
    )
    canonical_path: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    extension: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    content_hash: Mapped[str | None] = mapped_column(Text)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at_fs: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    exists_now: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    device: Mapped[Device] = relationship(back_populates="file_entities")


class FolderEntity(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "folder_entities"
    __table_args__ = (
        UniqueConstraint("device_id", "canonical_path", name="uq_folder_entities_device_path"),
        Index("idx_folder_entities_device_id", "device_id"),
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id"),
        nullable=False,
    )
    canonical_path: Mapped[str] = mapped_column(Text, nullable=False)
    folder_name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_path: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    exists_now: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    device: Mapped[Device] = relationship(back_populates="folder_entities")


class PlanAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plan_actions"
    __table_args__ = (
        Index("idx_plan_actions_plan_id", "plan_id"),
        Index("idx_plan_actions_status", "status"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id"),
        nullable=False,
    )
    action_type: Mapped[ActionType] = mapped_column(action_type_enum, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    status: Mapped[ActionStatus] = mapped_column(
        action_status_enum,
        nullable=False,
        server_default=text("'PENDING'"),
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    plan: Mapped[Plan] = relationship(back_populates="actions")


class MemoryEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "memory_events"
    __table_args__ = (
        CheckConstraint("confidence >= 0.000 AND confidence <= 1.000", name="ck_memory_events_confidence"),
        Index("idx_memory_events_user_id", "user_id"),
        Index("idx_memory_events_session_id", "session_id"),
        Index("idx_memory_events_event_type", "event_type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id"),
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
    )
    event_type: Mapped[EventType] = mapped_column(event_type_enum, nullable=False)
    scope_type: Mapped[str | None] = mapped_column(Text)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    pre_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    intended_change_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    action_taken_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    post_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    outcome: Mapped[OutcomeType | None] = mapped_column(outcome_type_enum)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="memory_events")
    device: Mapped[Device | None] = relationship(back_populates="memory_events")
    session: Mapped[Session | None] = relationship(back_populates="memory_events")


class UserPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "preference_key", name="uq_user_preferences_user_key"),
        CheckConstraint("confidence >= 0.000 AND confidence <= 1.000", name="ck_user_preferences_confidence"),
        Index("idx_user_preferences_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    preference_key: Mapped[str] = mapped_column(Text, nullable=False)
    preference_value_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        server_default=text("1.000"),
    )
    source: Mapped[SourceType] = mapped_column(source_type_enum, nullable=False)

    user: Mapped[User] = relationship(back_populates="preferences")


class OperationalPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "operational_policies"
    __table_args__ = (
        Index("idx_operational_policies_user_id", "user_id"),
        Index("idx_operational_policies_active", "is_active"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    policy_name: Mapped[str] = mapped_column(Text, nullable=False)
    policy_type: Mapped[PolicyType] = mapped_column(policy_type_enum, nullable=False)
    policy_text: Mapped[str] = mapped_column(Text, nullable=False)
    policy_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    user: Mapped[User] = relationship(back_populates="policies")
