.PHONY: help docs-gates cross-repo-agent

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "%-20s %s\n", $$1, $$2}'

# The five documentation gates also listed in AGENTS.md. Each detector runs its
# --selftest first, because a gate that cannot fail is the same as no gate.
docs-gates: ## Run the documentation gates (naming, number parity, headings, detector mutations, writing style)
	python3 scripts/check-fsx-naming.py --selftest
	python3 scripts/check-fsx-naming.py
	python3 scripts/check-doc-number-parity.py --selftest
	python3 scripts/check-doc-number-parity.py
	python3 scripts/check-heading-style.py --selftest
	python3 scripts/check-heading-style.py
	python3 scripts/check-detector-mutations.py
	python3 scripts/ai_style_rules.py docs/ --fail

cross-repo-agent: docs-gates ## Run quality gates and emit cross-repo notifications for Kiro Bot
	@mkdir -p docs/agent/notifications
	@python3 ~/.kiro/hooks/scripts/cross_repo_agent.py run 2>/dev/null || true
	@echo "cross-repo-agent: gates passed. Notifications written to docs/agent/notifications/ if any."
