CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    timezone TEXT DEFAULT 'UTC',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    device_type device_type_enum NOT NULL,
    hostname TEXT,
    os TEXT,
    local_agent_version TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    device_id UUID REFERENCES devices(id),
    title TEXT,
    mode session_mode_enum NOT NULL DEFAULT 'CHAT',
    status session_status_enum NOT NULL DEFAULT 'ACTIVE',
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ,
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE session_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    role role_type_enum NOT NULL,
    content TEXT NOT NULL,
    tool_name TEXT,
    tool_call_id TEXT,
    metadata_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    plan_type TEXT NOT NULL DEFAULT 'FILE_REORGANIZATION',
    goal TEXT NOT NULL,
    plan_json JSONB NOT NULL,
    rationale_summary TEXT,
    status plan_status_enum NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE task_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) UNIQUE,
    goal TEXT,
    current_step TEXT,
    active_plan_id UUID REFERENCES plans(id),
    active_entities_json JSONB,
    pending_action_ids_json JSONB,
    scratchpad_summary TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE file_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id),
    canonical_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    extension TEXT,
    mime_type TEXT,
    size_bytes BIGINT,
    content_hash TEXT,
    modified_at TIMESTAMPTZ,
    created_at_fs TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ DEFAULT now(),
    exists_now BOOLEAN DEFAULT true,
    metadata_json JSONB,
    UNIQUE (device_id, canonical_path)
);

CREATE TABLE folder_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES devices(id),
    canonical_path TEXT NOT NULL,
    folder_name TEXT NOT NULL,
    parent_path TEXT,
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ DEFAULT now(),
    exists_now BOOLEAN DEFAULT true,
    metadata_json JSONB,
    UNIQUE (device_id, canonical_path)
);

CREATE TABLE plan_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES plans(id),
    action_type action_type_enum NOT NULL,
    target_type TEXT NOT NULL,
    target_id UUID,
    action_payload_json JSONB NOT NULL,
    requires_approval BOOLEAN NOT NULL DEFAULT true,
    status action_status_enum NOT NULL DEFAULT 'PENDING',
    result_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE memory_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    device_id UUID REFERENCES devices(id),
    session_id UUID REFERENCES sessions(id),
    event_type event_type_enum NOT NULL,
    scope_type TEXT,
    scope_id UUID,
    pre_state_json JSONB,
    intended_change_json JSONB,
    action_taken_json JSONB,
    post_state_json JSONB,
    outcome outcome_type_enum,
    confidence NUMERIC(4,3) CHECK (confidence >= 0.000 AND confidence <= 1.000),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    preference_key TEXT NOT NULL,
    preference_value_json JSONB NOT NULL,
    confidence NUMERIC(4,3) DEFAULT 1.000 CHECK (confidence >= 0.000 AND confidence <= 1.000),
    source source_type_enum NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, preference_key)
);

CREATE TABLE operational_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    policy_name TEXT NOT NULL,
    policy_type policy_type_enum NOT NULL,
    policy_text TEXT NOT NULL,
    policy_json JSONB,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_devices_user_id ON devices(user_id);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_device_id ON sessions(device_id);
CREATE INDEX idx_session_messages_session_id ON session_messages(session_id);
CREATE INDEX idx_plans_session_id ON plans(session_id);
CREATE INDEX idx_plans_status ON plans(status);
CREATE INDEX idx_task_state_active_plan_id ON task_state(active_plan_id);
CREATE INDEX idx_file_entities_device_id ON file_entities(device_id);
CREATE INDEX idx_folder_entities_device_id ON folder_entities(device_id);
CREATE INDEX idx_plan_actions_plan_id ON plan_actions(plan_id);
CREATE INDEX idx_plan_actions_status ON plan_actions(status);
CREATE INDEX idx_memory_events_user_id ON memory_events(user_id);
CREATE INDEX idx_memory_events_session_id ON memory_events(session_id);
CREATE INDEX idx_memory_events_event_type ON memory_events(event_type);
CREATE INDEX idx_user_preferences_user_id ON user_preferences(user_id);
CREATE INDEX idx_operational_policies_user_id ON operational_policies(user_id);
CREATE INDEX idx_operational_policies_active ON operational_policies(is_active);