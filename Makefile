PYTHON ?= python
PYTHONPATH := src

.PHONY: bootstrap clean cold-start delivery-gate dependencies doctor format instructions lint manifest map quality quality-strict schemas smoke test typecheck validate

doctor:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline doctor --root .

bootstrap:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline bootstrap --root . --profile local --prepare

smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline smoke --root . --profile ci

dependencies:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline dependencies validate --root . --verify-installed

schemas:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline schemas check --root .

validate:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/validate_instructions.py --root .
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline validate --root .

instructions:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/validate_instructions.py --root .

cold-start:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/instruction_cold_start.py --root .

delivery-gate:
	@test -n "$(BASE_REF)" || (echo "BASE_REF is required" && exit 2)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline assurance delivery-gate --root . --base-ref $(BASE_REF) --head-ref HEAD

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest -q

lint:
	ruff check src tests

format:
	ruff format src tests

typecheck:
	mypy

quality:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline quality --root .

quality-strict:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline quality --root . --strict-tools --coverage

map:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline map --root .

manifest:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m project_pipeline manifest --root .

clean:
	$(PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(p, ignore_errors=True) for p in map(Path, ('.local','.pytest_cache','.mypy_cache','.ruff_cache','build','dist','htmlcov'))]"
