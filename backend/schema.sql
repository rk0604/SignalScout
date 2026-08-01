-- SignalScout schema (PostgreSQL / Neon)
-- OPTIONAL: the app auto-creates all of this on first boot via
--   flask --app app init-db      (or simply: python app.py)
-- Use this file only if you want to provision the schema by hand.
-- Generated from the SQLAlchemy models; keep in sync via that command.

CREATE TABLE IF NOT EXISTS agent_proposal (
	id UUID NOT NULL, 
	actor_email VARCHAR(120) NOT NULL, 
	ticker VARCHAR(32) NOT NULL, 
	action VARCHAR(16) NOT NULL, 
	shares INTEGER NOT NULL, 
	rationale TEXT, 
	confidence VARCHAR(16), 
	evidence_used JSONB, 
	risks TEXT, 
	snapshot_refs JSONB, 
	backtest_run_id UUID, 
	agent_run_id UUID, 
	model VARCHAR(64), 
	status VARCHAR(16) NOT NULL, 
	decided_at TIMESTAMP WITH TIME ZONE, 
	decision_note TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_agent_proposal_actor_email ON agent_proposal (actor_email);

CREATE TABLE IF NOT EXISTS agent_run (
	id UUID NOT NULL, 
	actor_email VARCHAR(120) NOT NULL, 
	model VARCHAR(64), 
	mode VARCHAR(16) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	steps INTEGER NOT NULL, 
	trace JSONB, 
	input_tokens INTEGER, 
	output_tokens INTEGER, 
	cost_usd FLOAT, 
	summary TEXT, 
	error TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_agent_run_actor_email ON agent_run (actor_email);

CREATE TABLE IF NOT EXISTS audit_log (
	id UUID NOT NULL, 
	actor_email VARCHAR(120), 
	action VARCHAR(64) NOT NULL, 
	entity VARCHAR(120), 
	payload JSONB, 
	snapshot_ref UUID, 
	request_id VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_audit_log_actor_email ON audit_log (actor_email);

CREATE TABLE IF NOT EXISTS backtest_run (
	id UUID NOT NULL, 
	actor_email VARCHAR(120), 
	strategy VARCHAR(64) NOT NULL, 
	params JSONB, 
	universe JSONB, 
	start_date VARCHAR(10), 
	end_date VARCHAR(10), 
	metrics JSONB, 
	equity_curve JSONB, 
	trades JSONB, 
	snapshot_refs JSONB, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_backtest_run_actor_email ON backtest_run (actor_email);

CREATE TABLE IF NOT EXISTS market_snapshot (
	id UUID NOT NULL, 
	ticker VARCHAR(32), 
	kind VARCHAR(32) NOT NULL, 
	payload JSONB NOT NULL, 
	fetched_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_market_snapshot_fetched_at ON market_snapshot (fetched_at);
CREATE INDEX IF NOT EXISTS ix_market_snapshot_kind ON market_snapshot (kind);
CREATE INDEX IF NOT EXISTS ix_market_snapshot_ticker ON market_snapshot (ticker);

CREATE TABLE IF NOT EXISTS user_data (
	id SERIAL NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	phone VARCHAR(120) NOT NULL, 
	password VARCHAR(255) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	UNIQUE (phone)
);

CREATE TABLE IF NOT EXISTS user_holdings (
	id UUID NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	ticker VARCHAR(120) NOT NULL, 
	avg_price NUMERIC(10, 2) NOT NULL, 
	num_shares INTEGER NOT NULL, 
	value NUMERIC(10, 2) NOT NULL, 
	pinned BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
);
