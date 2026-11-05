-- Free-form feedback for the temporary old-user subscription launch.
-- Applying this migration does not send messages or enroll users.
BEGIN;

CREATE TABLE IF NOT EXISTS old_user_feedback (
    feedback_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    username TEXT,
    feedback_text TEXT NOT NULL CHECK (length(btrim(feedback_text)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_old_user_feedback_created_at
    ON old_user_feedback(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_old_user_feedback_user_id
    ON old_user_feedback(user_id);

COMMIT;
