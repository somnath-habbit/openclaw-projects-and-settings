from Auto_job_application.flow.auto_apply_batch import AutoApplyFlow

if __name__ == "__main__":
    flow = AutoApplyFlow()
    flow.run(limit=0, apply_limit=10, skip_discovery=True)
