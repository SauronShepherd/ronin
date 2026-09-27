ALTER TABLE task_runs ADD COLUMN branch_decision_json TEXT;
CREATE INDEX idx_task_runs_branch_state
    ON task_runs(workspace_id, workflow_run_id, state, task_run_id);
