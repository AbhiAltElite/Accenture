.PHONY: setup gen demo test bench status audit guardrails verify-ai lint clean

setup:            ## create venv and install dependencies
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

gen:              ## generate the synthetic dataset + ground truth
	.venv/bin/python -m datagen.build

demo:             ## run the console at http://localhost:8000
	.venv/bin/uvicorn api.main:app --reload --port 8000

test:             ## run the test suite (includes the invariant tests)
	.venv/bin/pytest -q

bench:            ## run the benchmark harness and print the report
	PYTHONPATH=. .venv/bin/python -m bench.run --report

status:           ## show what the engine currently knows
	.venv/bin/python -m whychain.inspect

guardrails:       ## watch the guardrails refuse bad input
	PYTHONPATH=. .venv/bin/python scripts/guardrails.py

verify-ai:        ## prove both model stages work before a demo depends on them
	PYTHONPATH=. .venv/bin/python scripts/verify_ai.py

audit:            ## run the security and logic checklists
	PYTHONPATH=. .venv/bin/python scripts/audit.py

lint:
	.venv/bin/ruff check .

clean:
	rm -rf data/warehouse/*.duckdb .pytest_cache __pycache__
