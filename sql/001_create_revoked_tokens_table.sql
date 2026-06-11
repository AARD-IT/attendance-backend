-- Revoked tokens table for token revocation tracking
-- Stores tokens that have been explicitly revoked (e.g., on logout or compromise detection)
-- Used as fallback when Supabase session verification is unavailable

CREATE TABLE IF NOT EXISTS revoked_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    jti TEXT NOT NULL COMMENT 'JWT ID claim for token identification',
    token_hash BIGINT NOT NULL COMMENT 'Hash of the token for quick lookup',
    revoked_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    reason TEXT DEFAULT 'logout' COMMENT 'Reason for revocation (logout, compromise, etc)',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- Create indexes for efficient lookups
CREATE INDEX idx_revoked_tokens_user_id ON revoked_tokens(user_id);
CREATE INDEX idx_revoked_tokens_jti ON revoked_tokens(jti);
CREATE INDEX idx_revoked_tokens_token_hash ON revoked_tokens(token_hash);
CREATE INDEX idx_revoked_tokens_revoked_at ON revoked_tokens(revoked_at);

-- Create unique constraint to prevent duplicate revocations
CREATE UNIQUE INDEX idx_revoked_tokens_user_jti ON revoked_tokens(user_id, jti);

-- Enable Row Level Security (RLS)
ALTER TABLE revoked_tokens ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only view their own revoked tokens
CREATE POLICY "users_can_view_own_revoked_tokens" ON revoked_tokens
    FOR SELECT
    USING (auth.uid() = user_id);

-- Policy: Service role can view and manage revoked tokens
CREATE POLICY "service_role_manage_revoked_tokens" ON revoked_tokens
    FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

-- Add comments for documentation
COMMENT ON TABLE revoked_tokens IS 'Stores revoked tokens for session management';
COMMENT ON COLUMN revoked_tokens.jti IS 'JWT ID claim used to identify tokens';
COMMENT ON COLUMN revoked_tokens.token_hash IS 'Hash of the full token for efficient revocation checks';
COMMENT ON COLUMN revoked_tokens.reason IS 'Reason for revocation: logout, compromise, admin_revoke, etc';
