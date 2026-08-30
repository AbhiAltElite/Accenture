.PHONY: setup gen demo test bench status audit guardrails smoke verify-ai capture-ai warm-ai readme-pdf docker docker-ai lint clean

setup:            ## create venv and install dependencies
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

gen-all:          ## generate every industry's dataset + ground truth
	PYTHONPATH=. .venv/bin/python -m datagen.build all

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

capture-ai:       ## run one case with the model and without, and keep both
	PYTHONPATH=. .venv/bin/python scripts/capture_contrast.py

readme-pdf:       ## render README.md to the PDF the portal accepts
	PYTHONPATH=. .venv/bin/python scripts/render_pdf.py README.md dist

docker:            ## run the console in a container, deterministic path
	docker compose up --build

docker-ai:        ## same, with an open-weight model running alongside it
	docker compose --profile ai up --build

smoke:            ## drive the running server the way a reader does
	.venv/bin/python scripts/smoke.py

warm-ai:          ## fill the model cache before a demo, so nothing waits on camera
	PYTHONPATH=. .venv/bin/python scripts/warm_ai.py

verify-ai:        ## prove both model stages work before a demo depends on them
	PYTHONPATH=. .venv/bin/python scripts/verify_ai.py

audit:            ## run the security and logic checklists
	PYTHONPATH=. .venv/bin/python scripts/audit.py

lint:
	.venv/bin/ruff check .

clean:
	rm -rf data/warehouse/*.duckdb .pytest_cache __pycache__
