CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE plan_status_enum AS ENUM (
    'DRAFT',
    'PENDING',
    'APPROVED',
    'REJECTED',
    'EXECUTED',
    'PARTIAL'
);

CREATE TYPE action_status_enum AS ENUM (
    'PENDING',
    'APPROVED',
    'REJECTED',
    'EXECUTED',
    'FAILED',
    'SKIPPED'
);

CREATE TYPE action_type_enum AS ENUM (
    'RENAME',
    'MOVE',
    'CREATE_FOLDER',
    'ARCHIVE',
    'CLASSIFY'
);

CREATE TYPE outcome_type_enum AS ENUM (
    'SUCCESS',
    'FAILED',
    'PARTIAL',
    'REJECTED',
    'CANCELLED'
);

CREATE TYPE session_mode_enum AS ENUM (
    'CHAT',
    'CLEANUP',
    'PLANNING'
);

CREATE TYPE session_status_enum AS ENUM (
    'ACTIVE',
    'PAUSED',
    'COMPLETED',
    'FAILED'
);

CREATE TYPE event_type_enum AS ENUM (
    'SCAN',
    'PLAN',
    'RENAME',
    'MOVE',
    'ARCHIVE',
    'CLASSIFY',
    'FAILURE',
    'APPROVAL',
    'REJECTION'
);

CREATE TYPE role_type_enum AS ENUM (
    'SYSTEM',
    'USER',
    'ASSISTANT',
    'TOOL'
);

CREATE TYPE policy_type_enum AS ENUM (
    'SAFETY',
    'NAMING',
    'ARCHIVE',
    'LEGAL',
    'REVIEW'
);

CREATE TYPE device_type_enum AS ENUM (
    'WINDOWS_PC',
    'MAC',
    'LAPTOP',
    'MAC_LAPTOP',
    'VM',
    'SERVER'
);

CREATE TYPE source_type_enum AS ENUM (
    'MODEL',
    'USER',
    'RULE',
    'TOOL',
    'EXPLICIT_USER',
    'INFERRED',
    'APPROVED'
);