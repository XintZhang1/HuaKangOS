-- REVIEW DRAFT ONLY. Not registered or applied.
-- Separate append-only Alembic revision required before enabling transfer v3.

CREATE TABLE transfer_exception_receipts (
	id SERIAL NOT NULL, 
	request_key VARCHAR(80) NOT NULL, 
	actor_id INTEGER NOT NULL, 
	digest VARCHAR(64) NOT NULL, 
	result JSON NOT NULL, 
	store_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_transfer_exception_request UNIQUE (store_id, request_key), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_transfer_exception_receipts_store_id ON transfer_exception_receipts (store_id);

CREATE TABLE transfer_exceptions (
	id SERIAL NOT NULL, 
	version INTEGER NOT NULL, 
	transfer_id INTEGER NOT NULL, 
	active_transfer_id INTEGER, 
	original_id INTEGER NOT NULL, 
	stage VARCHAR(15) NOT NULL, 
	finding VARCHAR(15) NOT NULL, 
	quantity_milli BIGINT NOT NULL, 
	value_cents BIGINT NOT NULL, 
	request_store_id INTEGER NOT NULL, 
	requested_by INTEGER NOT NULL, 
	reason VARCHAR(1000) NOT NULL, 
	due_date DATE NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_transfer_exception_origin CHECK (stage IN ('outbound','rejected','returning') AND finding IN ('missing','damaged')), 
	CONSTRAINT ck_transfer_exception_amount CHECK (quantity_milli>0 AND value_cents>=0), 
	CONSTRAINT ck_transfer_exception_status CHECK (status IN ('investigating','review','approved','disposed','posted','cancelled')), 
	CONSTRAINT ck_transfer_exception_active CHECK ((status IN ('posted','cancelled') AND active_transfer_id IS NULL) OR (status NOT IN ('posted','cancelled') AND active_transfer_id IS NOT NULL AND active_transfer_id=transfer_id)), 
	FOREIGN KEY(transfer_id) REFERENCES material_transfers (id), 
	UNIQUE (active_transfer_id), 
	FOREIGN KEY(active_transfer_id) REFERENCES material_transfers (id), 
	FOREIGN KEY(original_id) REFERENCES material_transfer_movements (id), 
	FOREIGN KEY(request_store_id) REFERENCES stores (id), 
	FOREIGN KEY(requested_by) REFERENCES users (id)
);

CREATE INDEX ix_transfer_exceptions_original_id ON transfer_exceptions (original_id);

CREATE INDEX ix_transfer_exceptions_transfer_id ON transfer_exceptions (transfer_id);

CREATE TABLE transfer_exception_cancellations (
	id SERIAL NOT NULL, 
	exception_id INTEGER NOT NULL, 
	store_id INTEGER NOT NULL, 
	reason VARCHAR(1000) NOT NULL, 
	evidence_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (exception_id), 
	FOREIGN KEY(exception_id) REFERENCES transfer_exceptions (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id), 
	FOREIGN KEY(evidence_id) REFERENCES flow_files (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE transfer_exception_observations (
	id SERIAL NOT NULL, 
	exception_id INTEGER NOT NULL, 
	store_id INTEGER NOT NULL, 
	observation VARCHAR(30) NOT NULL, 
	quantity_milli BIGINT NOT NULL, 
	result VARCHAR(1000) NOT NULL, 
	evidence_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	business_date DATE NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_transfer_exception_observation CHECK (observation IN ('dispatch_verified','return_dispatch_verified','missing','held_damaged') AND quantity_milli>0), 
	FOREIGN KEY(exception_id) REFERENCES transfer_exceptions (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id), 
	FOREIGN KEY(evidence_id) REFERENCES flow_files (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_transfer_exception_observations_exception_id ON transfer_exception_observations (exception_id);

CREATE TABLE transfer_recovery_claims (
	exception_id INTEGER NOT NULL, 
	counterparty_kind VARCHAR(12) NOT NULL, 
	supplier_id INTEGER, 
	insurer_id INTEGER, 
	counterparty_snapshot JSON NOT NULL, 
	requested_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	id SERIAL NOT NULL, 
	version INTEGER NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	store_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_transfer_recovery_party CHECK ((counterparty_kind='carrier' AND supplier_id IS NOT NULL AND insurer_id IS NULL) OR (counterparty_kind='insurer' AND insurer_id IS NOT NULL AND supplier_id IS NULL)), 
	FOREIGN KEY(exception_id) REFERENCES transfer_exceptions (id), 
	FOREIGN KEY(supplier_id) REFERENCES master_suppliers (id), 
	FOREIGN KEY(insurer_id) REFERENCES master_insurers (id), 
	FOREIGN KEY(requested_by) REFERENCES users (id)
);

CREATE INDEX ix_transfer_recovery_claims_exception_id ON transfer_recovery_claims (exception_id);

CREATE INDEX ix_transfer_recovery_claims_store_id ON transfer_recovery_claims (store_id);

CREATE TABLE transfer_exception_plans (
	id SERIAL NOT NULL, 
	exception_id INTEGER NOT NULL, 
	revision INTEGER NOT NULL, 
	source_observation_id INTEGER NOT NULL, 
	destination_observation_id INTEGER NOT NULL, 
	source_bearer_cents BIGINT NOT NULL, 
	destination_bearer_cents BIGINT NOT NULL, 
	reason VARCHAR(1000) NOT NULL, 
	evidence_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_transfer_exception_plan_revision UNIQUE (exception_id, revision), 
	CONSTRAINT ck_transfer_exception_plan_amount CHECK (revision>0 AND source_bearer_cents>=0 AND destination_bearer_cents>=0), 
	FOREIGN KEY(exception_id) REFERENCES transfer_exceptions (id), 
	FOREIGN KEY(source_observation_id) REFERENCES transfer_exception_observations (id), 
	FOREIGN KEY(destination_observation_id) REFERENCES transfer_exception_observations (id), 
	FOREIGN KEY(evidence_id) REFERENCES flow_files (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_transfer_exception_plans_exception_id ON transfer_exception_plans (exception_id);

CREATE TABLE transfer_recovery_plans (
	id SERIAL NOT NULL, 
	claim_id INTEGER NOT NULL, 
	revision INTEGER NOT NULL, 
	target_cents BIGINT NOT NULL, 
	due_date DATE NOT NULL, 
	reason VARCHAR(1000) NOT NULL, 
	evidence_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	store_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_transfer_recovery_revision UNIQUE (claim_id, revision), 
	CONSTRAINT ck_transfer_recovery_target CHECK (target_cents>=0), 
	FOREIGN KEY(claim_id) REFERENCES transfer_recovery_claims (id), 
	FOREIGN KEY(evidence_id) REFERENCES flow_files (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_transfer_recovery_plans_claim_id ON transfer_recovery_plans (claim_id);

CREATE INDEX ix_transfer_recovery_plans_store_id ON transfer_recovery_plans (store_id);

CREATE TABLE transfer_exception_disposals (
	id SERIAL NOT NULL, 
	exception_id INTEGER NOT NULL, 
	plan_id INTEGER NOT NULL, 
	store_id INTEGER NOT NULL, 
	quantity_milli BIGINT NOT NULL, 
	method VARCHAR(1000) NOT NULL, 
	evidence_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	business_date DATE NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_transfer_exception_disposal_quantity CHECK (quantity_milli>0), 
	UNIQUE (exception_id), 
	FOREIGN KEY(exception_id) REFERENCES transfer_exceptions (id), 
	FOREIGN KEY(plan_id) REFERENCES transfer_exception_plans (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id), 
	FOREIGN KEY(evidence_id) REFERENCES flow_files (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE transfer_exception_reviews (
	id SERIAL NOT NULL, 
	plan_id INTEGER NOT NULL, 
	store_id INTEGER NOT NULL, 
	decision VARCHAR(10) NOT NULL, 
	reason VARCHAR(1000) NOT NULL, 
	evidence_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_transfer_exception_review_party UNIQUE (plan_id, store_id), 
	CONSTRAINT ck_transfer_exception_review_decision CHECK (decision IN ('approve','reject')), 
	FOREIGN KEY(plan_id) REFERENCES transfer_exception_plans (id), 
	FOREIGN KEY(store_id) REFERENCES stores (id), 
	FOREIGN KEY(evidence_id) REFERENCES flow_files (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_transfer_exception_reviews_plan_id ON transfer_exception_reviews (plan_id);

CREATE TABLE transfer_loss_postings (
	id SERIAL NOT NULL, 
	exception_id INTEGER NOT NULL, 
	transfer_id INTEGER NOT NULL, 
	line_id INTEGER NOT NULL, 
	original_id INTEGER NOT NULL, 
	plan_id INTEGER NOT NULL, 
	quantity_milli BIGINT NOT NULL, 
	value_cents BIGINT NOT NULL, 
	source_bearer_cents BIGINT NOT NULL, 
	destination_bearer_cents BIGINT NOT NULL, 
	evidence_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	business_date DATE NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	store_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_transfer_loss_conservation CHECK (quantity_milli>0 AND value_cents>=0 AND source_bearer_cents>=0 AND destination_bearer_cents>=0 AND source_bearer_cents+destination_bearer_cents=value_cents), 
	UNIQUE (exception_id), 
	FOREIGN KEY(exception_id) REFERENCES transfer_exceptions (id), 
	FOREIGN KEY(transfer_id) REFERENCES material_transfers (id), 
	FOREIGN KEY(line_id) REFERENCES material_transfer_lines (id), 
	FOREIGN KEY(original_id) REFERENCES material_transfer_movements (id), 
	UNIQUE (plan_id), 
	FOREIGN KEY(plan_id) REFERENCES transfer_exception_plans (id), 
	FOREIGN KEY(evidence_id) REFERENCES flow_files (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_transfer_loss_postings_line_id ON transfer_loss_postings (line_id);

CREATE INDEX ix_transfer_loss_postings_store_id ON transfer_loss_postings (store_id);

CREATE INDEX ix_transfer_loss_postings_transfer_id ON transfer_loss_postings (transfer_id);

CREATE TABLE transfer_recovery_cancellations (
	id SERIAL NOT NULL, 
	plan_id INTEGER NOT NULL, 
	reason VARCHAR(1000) NOT NULL, 
	evidence_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	store_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (plan_id), 
	FOREIGN KEY(plan_id) REFERENCES transfer_recovery_plans (id), 
	FOREIGN KEY(evidence_id) REFERENCES flow_files (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_transfer_recovery_cancellations_store_id ON transfer_recovery_cancellations (store_id);

CREATE TABLE transfer_recovery_payments (
	id SERIAL NOT NULL, 
	claim_id INTEGER NOT NULL, 
	plan_id INTEGER NOT NULL, 
	original_id INTEGER, 
	direction VARCHAR(3) NOT NULL, 
	amount_cents BIGINT NOT NULL, 
	account_id INTEGER NOT NULL, 
	reference VARCHAR(100) NOT NULL, 
	cash_id INTEGER NOT NULL, 
	evidence_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	business_date DATE NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	store_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_transfer_recovery_payment CHECK (amount_cents>0 AND ((direction='in' AND original_id IS NULL) OR (direction='out' AND original_id IS NOT NULL))), 
	FOREIGN KEY(claim_id) REFERENCES transfer_recovery_claims (id), 
	FOREIGN KEY(plan_id) REFERENCES transfer_recovery_plans (id), 
	FOREIGN KEY(original_id) REFERENCES transfer_recovery_payments (id), 
	FOREIGN KEY(account_id) REFERENCES flow_accounts (id), 
	UNIQUE (cash_id), 
	FOREIGN KEY(cash_id) REFERENCES cash_entries (id), 
	FOREIGN KEY(evidence_id) REFERENCES flow_files (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_transfer_recovery_payments_claim_id ON transfer_recovery_payments (claim_id);

CREATE INDEX ix_transfer_recovery_payments_store_id ON transfer_recovery_payments (store_id);

CREATE TABLE transfer_recovery_reviews (
	id SERIAL NOT NULL, 
	plan_id INTEGER NOT NULL, 
	decision VARCHAR(10) NOT NULL, 
	reason VARCHAR(1000) NOT NULL, 
	evidence_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	business_date DATE NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	store_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_transfer_recovery_review CHECK (decision IN ('approve','reject')), 
	UNIQUE (plan_id), 
	FOREIGN KEY(plan_id) REFERENCES transfer_recovery_plans (id), 
	FOREIGN KEY(evidence_id) REFERENCES flow_files (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE INDEX ix_transfer_recovery_reviews_store_id ON transfer_recovery_reviews (store_id);

CREATE TABLE transfer_loss_settlements (
	id SERIAL NOT NULL, 
	transfer_id INTEGER NOT NULL, 
	posting_id INTEGER NOT NULL, 
	exception_id INTEGER NOT NULL, 
	counterparty_store_id INTEGER NOT NULL, 
	amount_cents BIGINT NOT NULL, 
	business_date DATE NOT NULL, 
	store_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_transfer_loss_settlement_party UNIQUE (posting_id, store_id), 
	CONSTRAINT ck_transfer_loss_settlement_amount CHECK (amount_cents!=0), 
	FOREIGN KEY(transfer_id) REFERENCES material_transfers (id), 
	FOREIGN KEY(posting_id) REFERENCES transfer_loss_postings (id), 
	FOREIGN KEY(exception_id) REFERENCES transfer_exceptions (id), 
	FOREIGN KEY(counterparty_store_id) REFERENCES stores (id)
);

CREATE INDEX ix_transfer_loss_settlements_exception_id ON transfer_loss_settlements (exception_id);

CREATE INDEX ix_transfer_loss_settlements_posting_id ON transfer_loss_settlements (posting_id);

CREATE INDEX ix_transfer_loss_settlements_store_id ON transfer_loss_settlements (store_id);

CREATE INDEX ix_transfer_loss_settlements_transfer_id ON transfer_loss_settlements (transfer_id);
