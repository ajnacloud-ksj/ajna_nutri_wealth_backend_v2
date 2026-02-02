-- ============================================
-- AI Model Configuration Tables
-- ============================================

-- 1. AI Providers Table
CREATE TABLE IF NOT EXISTS ai_providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) UNIQUE NOT NULL,  -- openai, groq, anthropic, ollama
    display_name VARCHAR(100) NOT NULL,
    base_url VARCHAR(255) NOT NULL,
    api_key_secret_name VARCHAR(255),  -- AWS Secrets Manager key name
    is_active BOOLEAN DEFAULT true,
    supports_images BOOLEAN DEFAULT true,
    supports_json_mode BOOLEAN DEFAULT true,
    max_retries INT DEFAULT 3,
    timeout_seconds INT DEFAULT 30,
    rate_limit_rpm INT,  -- Requests per minute
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. AI Models Table
CREATE TABLE IF NOT EXISTS ai_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id UUID REFERENCES ai_providers(id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,  -- gpt-4o-mini, llama-3.3-70b-versatile
    display_name VARCHAR(200),
    model_version VARCHAR(50),

    -- Capabilities
    context_window INT DEFAULT 4096,
    max_tokens INT DEFAULT 500,
    supports_images BOOLEAN DEFAULT false,
    supports_functions BOOLEAN DEFAULT false,

    -- Cost (per 1K tokens)
    cost_per_1k_input DECIMAL(10,6) DEFAULT 0.001,
    cost_per_1k_output DECIMAL(10,6) DEFAULT 0.001,

    -- Performance
    avg_response_time_ms INT,  -- Track actual performance
    success_rate DECIMAL(5,2),  -- Track reliability

    -- Status
    is_active BOOLEAN DEFAULT true,
    is_deprecated BOOLEAN DEFAULT false,
    deprecation_date DATE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(provider_id, model_name)
);

-- 3. Model Assignments (which model to use for what)
CREATE TABLE IF NOT EXISTS ai_model_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL,  -- Support multi-tenant
    use_case VARCHAR(50) NOT NULL,  -- classifier, food, receipt, workout
    primary_model_id UUID REFERENCES ai_models(id),
    fallback_model_id UUID REFERENCES ai_models(id),

    -- A/B Testing
    experiment_model_id UUID REFERENCES ai_models(id),
    experiment_percentage INT DEFAULT 0,  -- % of traffic to experiment

    -- Settings
    temperature DECIMAL(2,1) DEFAULT 0.0,
    max_tokens INT DEFAULT 500,
    custom_prompt TEXT,

    -- Performance tracking
    total_requests INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    total_cost DECIMAL(10,4) DEFAULT 0,
    avg_latency_ms INT,

    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(tenant_id, use_case)
);

-- 4. Model Performance Metrics
CREATE TABLE IF NOT EXISTS ai_model_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id UUID REFERENCES ai_models(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    hour INT,  -- 0-23 for hourly metrics

    -- Usage metrics
    request_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    timeout_count INT DEFAULT 0,

    -- Performance metrics
    avg_latency_ms INT,
    p50_latency_ms INT,
    p95_latency_ms INT,
    p99_latency_ms INT,

    -- Token usage
    total_input_tokens INT DEFAULT 0,
    total_output_tokens INT DEFAULT 0,

    -- Cost
    total_cost DECIMAL(10,4) DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(model_id, date, hour)
);

-- 5. Model Request Log (for debugging and analysis)
CREATE TABLE IF NOT EXISTS ai_request_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) UNIQUE NOT NULL,
    user_id VARCHAR(100),
    tenant_id VARCHAR(100),

    -- Model info
    model_id UUID REFERENCES ai_models(id),
    use_case VARCHAR(50),

    -- Request details
    prompt_tokens INT,
    completion_tokens INT,
    total_tokens INT,

    -- Performance
    latency_ms INT,
    status VARCHAR(20),  -- success, error, timeout
    error_message TEXT,

    -- Cost
    cost DECIMAL(10,6),

    -- Metadata
    category VARCHAR(50),  -- food, receipt, workout
    confidence DECIMAL(3,2),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for analytics
    INDEX idx_user_date (user_id, created_at),
    INDEX idx_model_date (model_id, created_at),
    INDEX idx_status (status, created_at)
);

-- 6. Model Prompts Library
CREATE TABLE IF NOT EXISTS ai_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    use_case VARCHAR(50) NOT NULL,
    version INT DEFAULT 1,

    -- Prompt templates
    system_prompt TEXT,
    user_prompt_template TEXT,

    -- Settings
    temperature DECIMAL(2,1) DEFAULT 0.0,
    max_tokens INT DEFAULT 500,
    response_format VARCHAR(20),  -- json, text, xml

    -- Metadata
    description TEXT,
    tags JSONB,

    is_active BOOLEAN DEFAULT true,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- Default Data
-- ============================================

-- Insert default providers
INSERT INTO ai_providers (name, display_name, base_url, api_key_secret_name, is_active)
VALUES
    ('openai', 'OpenAI', 'https://api.openai.com/v1', 'openai-api-key', true),
    ('groq', 'Groq', 'https://api.groq.com/openai/v1', 'groq-api-key', true),
    ('anthropic', 'Anthropic', 'https://api.anthropic.com/v1', 'anthropic-api-key', false),
    ('ollama', 'Ollama (Local)', 'http://localhost:11434/v1', null, false)
ON CONFLICT (name) DO NOTHING;

-- Insert OpenAI models
INSERT INTO ai_models (provider_id, model_name, display_name, context_window, max_tokens, cost_per_1k_input, cost_per_1k_output, supports_images)
SELECT
    p.id,
    m.model_name,
    m.display_name,
    m.context_window,
    m.max_tokens,
    m.cost_input,
    m.cost_output,
    m.supports_images
FROM ai_providers p
CROSS JOIN (VALUES
    ('gpt-4o-mini', 'GPT-4 Omni Mini', 128000, 16000, 0.00015, 0.0006, true),
    ('gpt-4o', 'GPT-4 Omni', 128000, 4096, 0.0025, 0.01, true),
    ('gpt-4-turbo', 'GPT-4 Turbo', 128000, 4096, 0.01, 0.03, true),
    ('gpt-3.5-turbo', 'GPT-3.5 Turbo', 16384, 4096, 0.0005, 0.0015, false)
) AS m(model_name, display_name, context_window, max_tokens, cost_input, cost_output, supports_images)
WHERE p.name = 'openai'
ON CONFLICT (provider_id, model_name) DO NOTHING;

-- Insert Groq models
INSERT INTO ai_models (provider_id, model_name, display_name, context_window, max_tokens, cost_per_1k_input, cost_per_1k_output, supports_images)
SELECT
    p.id,
    m.model_name,
    m.display_name,
    m.context_window,
    m.max_tokens,
    m.cost_input,
    m.cost_output,
    m.supports_images
FROM ai_providers p
CROSS JOIN (VALUES
    ('llama-3.3-70b-versatile', 'Llama 3.3 70B', 128000, 8192, 0.00059, 0.00079, false),
    ('llama-3.2-90b-vision', 'Llama 3.2 90B Vision', 128000, 8192, 0.0009, 0.0009, true),
    ('mixtral-8x7b-32768', 'Mixtral 8x7B', 32768, 32768, 0.00024, 0.00024, false)
) AS m(model_name, display_name, context_window, max_tokens, cost_input, cost_output, supports_images)
WHERE p.name = 'groq'
ON CONFLICT (provider_id, model_name) DO NOTHING;

-- ============================================
-- Views for Easy Access
-- ============================================

-- View: Available models with provider info
CREATE OR REPLACE VIEW v_available_models AS
SELECT
    m.id,
    p.name as provider,
    m.model_name,
    m.display_name,
    m.context_window,
    m.max_tokens,
    m.cost_per_1k_input,
    m.cost_per_1k_output,
    m.supports_images,
    m.avg_response_time_ms,
    m.success_rate,
    m.is_active
FROM ai_models m
JOIN ai_providers p ON m.provider_id = p.id
WHERE m.is_active = true AND p.is_active = true
ORDER BY p.name, m.cost_per_1k_input;

-- View: Current model assignments per tenant
CREATE OR REPLACE VIEW v_model_assignments AS
SELECT
    ma.tenant_id,
    ma.use_case,
    pm.model_name as primary_model,
    pp.name as primary_provider,
    fm.model_name as fallback_model,
    fp.name as fallback_provider,
    ma.experiment_percentage,
    ma.total_requests,
    ma.total_cost,
    ma.avg_latency_ms
FROM ai_model_assignments ma
LEFT JOIN ai_models pm ON ma.primary_model_id = pm.id
LEFT JOIN ai_providers pp ON pm.provider_id = pp.id
LEFT JOIN ai_models fm ON ma.fallback_model_id = fm.id
LEFT JOIN ai_providers fp ON fm.provider_id = fp.id
WHERE ma.is_active = true;

-- ============================================
-- Functions
-- ============================================

-- Function to get the best model for a use case
CREATE OR REPLACE FUNCTION get_model_for_use_case(
    p_tenant_id VARCHAR,
    p_use_case VARCHAR
) RETURNS TABLE (
    model_id UUID,
    provider_name VARCHAR,
    model_name VARCHAR,
    base_url VARCHAR,
    api_key_secret VARCHAR,
    temperature DECIMAL,
    max_tokens INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id as model_id,
        p.name as provider_name,
        m.model_name,
        p.base_url,
        p.api_key_secret_name,
        COALESCE(ma.temperature, 0.0) as temperature,
        COALESCE(ma.max_tokens, m.max_tokens) as max_tokens
    FROM ai_model_assignments ma
    JOIN ai_models m ON ma.primary_model_id = m.id
    JOIN ai_providers p ON m.provider_id = p.id
    WHERE ma.tenant_id = p_tenant_id
    AND ma.use_case = p_use_case
    AND ma.is_active = true
    AND m.is_active = true
    AND p.is_active = true
    LIMIT 1;

    -- If no assignment found, return default
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT
            m.id as model_id,
            p.name as provider_name,
            m.model_name,
            p.base_url,
            p.api_key_secret_name,
            0.0 as temperature,
            m.max_tokens
        FROM ai_models m
        JOIN ai_providers p ON m.provider_id = p.id
        WHERE p.name = 'openai'
        AND m.model_name = 'gpt-4o-mini'
        AND m.is_active = true
        LIMIT 1;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to log model usage
CREATE OR REPLACE FUNCTION log_model_usage(
    p_request_id VARCHAR,
    p_model_id UUID,
    p_user_id VARCHAR,
    p_tokens INT,
    p_latency_ms INT,
    p_status VARCHAR,
    p_cost DECIMAL
) RETURNS VOID AS $$
BEGIN
    -- Insert into request log
    INSERT INTO ai_request_log (
        request_id, model_id, user_id, total_tokens,
        latency_ms, status, cost, created_at
    ) VALUES (
        p_request_id, p_model_id, p_user_id, p_tokens,
        p_latency_ms, p_status, p_cost, NOW()
    );

    -- Update model metrics
    INSERT INTO ai_model_metrics (
        model_id, date, hour, request_count,
        total_input_tokens, total_cost
    ) VALUES (
        p_model_id, CURRENT_DATE, EXTRACT(HOUR FROM NOW()),
        1, p_tokens, p_cost
    )
    ON CONFLICT (model_id, date, hour) DO UPDATE
    SET
        request_count = ai_model_metrics.request_count + 1,
        total_input_tokens = ai_model_metrics.total_input_tokens + p_tokens,
        total_cost = ai_model_metrics.total_cost + p_cost;

    -- Update assignment metrics
    UPDATE ai_model_assignments
    SET
        total_requests = total_requests + 1,
        total_tokens = total_tokens + p_tokens,
        total_cost = total_cost + p_cost
    WHERE primary_model_id = p_model_id;
END;
$$ LANGUAGE plpgsql;