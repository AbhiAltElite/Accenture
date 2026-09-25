.PHONY: help run app package demo-reset real-data prepare setup gen gen-all demo test bench scale status audit guardrails smoke verify-ai capture-ai warm-ai readme-pdf docker docker-ai lint check-attribution ci clean

# `make` with no target lists the targets, so the entry point to this
# repository is the same command whether or not you have read the README.
.DEFAULT_GOAL := help

help:             ## list the targets in this file
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'


run:              ## one command: environment, data, server, browser, model check
	./run.sh

app:              ## build WhyChain.app: double-click to open the console in its own window
	./app/build_mac_app.sh

package-offline:  ## one zip per machine type with Python inside: unzip, double-click, no internet
	./app/build_mac_app.sh >/dev/null
	.venv/bin/python app/package.py --bundle win mac-arm mac-intel $(ARGS)

package:          ## one zip that runs on another PC: code, data, AI cache, key (see app/package.py)
	./app/build_mac_app.sh >/dev/null
	.venv/bin/python app/package.py $(ARGS)

demo-reset:       ## start the demo clean: archive signatures, decisions and feedback (nothing is deleted)
	@stamp=$$(date +%Y%m%d-%H%M%S); dest=data/archive/$$stamp; moved=0; \
	for f in data/audit/audit.jsonl data/feedback/feedback.jsonl data/feedback/applied.jsonl; do \
	  if [ -s $$f ]; then mkdir -p $$dest; mv $$f $$dest/; moved=1; fi; done; \
	if [ $$moved = 1 ]; then echo "Archived to $$dest. The audit trail and feedback start empty."; \
	else echo "Nothing to archive; already clean."; fi

setup:            ## install and verify everything this folder needs (the app's own installer)
	WHYCHAIN_APP_QUIET=1 python3 app/launch.py --setup

gen-all:          ## generate every industry's dataset + ground truth
	PYTHONPATH=. .venv/bin/python -m datagen.build all
	$(MAKE) prepare

gen:              ## generate the synthetic dataset + ground truth
	.venv/bin/python -m datagen.build
	$(MAKE) prepare ARGS=retail

prepare:          ## compute each contract's lineage once, at ingest, not per read
	PYTHONPATH=. .venv/bin/python scripts/prepare.py $(ARGS)

demo:             ## run the console at http://localhost:8000
	.venv/bin/python -m uvicorn api.main:app --reload --port 8000

test:             ## run the test suite (includes the invariant tests)
	.venv/bin/python -m pytest -q

bench:            ## run the benchmark harness and print the report
	PYTHONPATH=. .venv/bin/python -m bench.run --report

scale:            ## measure what happens with more data and more readers
	PYTHONPATH=. .venv/bin/python -m bench.scale $(ARGS)

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

real-data:        ## run the engine on a public dataset nobody here generated
	PYTHONPATH=. .venv/bin/python scripts/real_data.py

audit:            ## run the security and logic checklists
	PYTHONPATH=. .venv/bin/python scripts/audit.py

lint:             ## static checks, the same ones CI runs
	.venv/bin/python -m ruff check .

check-attribution: ## the guard CI runs over the commit history
	./.github/scripts/check-attribution.sh

ci:               ## everything CI runs, in CI's order
	$(MAKE) lint
	$(MAKE) gen
	$(MAKE) test
	.venv/bin/python -m pytest -m invariant -q
	$(MAKE) check-attribution

clean:            ## remove generated data and caches
	rm -rf data/warehouse/*.duckdb .pytest_cache __pycache__
