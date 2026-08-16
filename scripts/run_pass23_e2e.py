from pathlib import Path
from project_pipeline.verification.e2e import write_full_e2e_report

if __name__ == "__main__":
    root=Path(__file__).resolve().parents[1]
    path=write_full_e2e_report(root)
    print(path.relative_to(root))
