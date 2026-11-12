.PHONY: help docs-gates cross-repo-agent

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "%-20s %s\n", $$1, $$2}'

# A subset of .github/workflows/docs-quality.yml. Detectors that have a --selftest run it
# first, because a gate that cannot fail is the same as no gate. Not covered here: EN/JA pair
# completeness, internal links, section-count parity, YAML syntax, support-case and name scans.
docs-gates: ## Run the documentation gates (naming, number parity, headings, detector mutations, writing style, tables, account IDs)
	python3 scripts/check-fsx-naming.py --selftest
	python3 scripts/check-fsx-naming.py
	python3 scripts/check-doc-number-parity.py --selftest
	python3 scripts/check-doc-number-parity.py
	python3 scripts/check-heading-style.py --selftest
	python3 scripts/check-heading-style.py
	python3 scripts/check-detector-mutations.py
	python3 scripts/ai_style_rules.py docs/ --fail
	git ls-files -- '*.md' | xargs python3 scripts/check-markdown-tables.py
	python3 scripts/check-account-ids.py

# Called by a local supervisor script that runs each repository's gates. Do not call that
# script from here: it calls this target, so doing both recurses until the timeout.
cross-repo-agent: docs-gates ## Run the gates for a local supervisor script (no recursion)
	@mkdir -p docs/agent/notifications
	@echo "cross-repo-agent: gates passed."
