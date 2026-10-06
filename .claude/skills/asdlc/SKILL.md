---
name: asdlc
description: La knowledge base ASDLC (Agentic Software Development Life Cycle) — concetti, pattern, pratiche e ricette per lavorare con agenti. Usa quando serve un articolo che AGENTS.md o il runner citano (es. patterns/adversarial-code-review, patterns/context-gates) o una lettura avversariale di una spec o di una PR.
---

# ASDLC — knowledge base

Copia di [`villetakanen/asdlc-io`](https://github.com/villetakanen/asdlc-io) allo sha `71d7ba2503128feadcd98bd60fad640dae13b801`, sotto licenza **MIT** (© Ville Takanen): il testo della licenza è in [`LICENSE`](LICENSE), qui accanto. Gli articoli sono copiati come sono.

75 articoli. Non si modifica a mano: si rigenera con `python3 tools/aggiorna_kb.py <sha>`, e lo sha da cui viene sta in [`UPSTREAM`](UPSTREAM) (`backlog/PBI-359`).

Per una sessione esplorativa a mano l'upstream espone anche un server MCP, `https://asdlc.io/mcp`: non è un canale del runner, che legge solo questa copia pinnata.

## concepts (39)

- [The 4D Framework (Anthropic)](concepts/4d-framework.md)
- [Agent Skills](concepts/agent-skills.md)
- [Agentic SDLC](concepts/agentic-sdlc.md)
- [AI Amplification](concepts/ai-amplification.md)
- [AI Software Factory](concepts/ai-software-factory.md)
- [Architecture Decision Record](concepts/architecture-decision-record.md)
- [Behavior-Driven Development](concepts/behavior-driven-development.md)
- [Compound Engineering](concepts/compound-engineering.md)
- [Context Anchoring](concepts/context-anchoring.md)
- [Context Engineering](concepts/context-engineering.md)
- [Coverage Metric](concepts/coverage-metric.md)
- [Digital Twins](concepts/digital-twins.md)
- [Event Modeling](concepts/event-modeling.md)
- [Extreme Programming](concepts/extreme-programming.md)
- [Feedback Loop Compression](concepts/feedback-loop-compression.md)
- [Gherkin](concepts/gherkin.md)
- [Guardrails](concepts/guardrails.md)
- [Harness Engineering](concepts/harness-engineering.md)
- [The Learning Loop](concepts/learning-loop.md)
- [Levels of Autonomy](concepts/levels-of-autonomy.md)
- [Mermaid](concepts/mermaid.md)
- [Model Context Protocol (MCP)](concepts/model-context-protocol.md)
- [Model-Driven Development](concepts/model-driven-development.md)
- [OODA Loop](concepts/ooda-loop.md)
- [PR Slop](concepts/pr-slop.md)
- [Product Requirement Prompt (PRP)](concepts/product-requirement-prompt.md)
- [Product Thinking](concepts/product-thinking.md)
- [Production Readiness Gap](concepts/production-readiness-gap.md)
- [Provenance](concepts/provenance.md)
- [ReAct Pattern](concepts/react-pattern.md)
- [Red Queen Gödel Machine](concepts/red-queen-godel-machine.md)
- [Request for Comments](concepts/request-for-comments.md)
- [Software Civil Engineering](concepts/software-civil-engineering.md)
- [Spec-Driven Development](concepts/spec-driven-development.md)
- [Test-Driven Development](concepts/test-driven-development.md)
- [Theory of LLM Constraints](concepts/theory-of-llm-constraints.md)
- [Triple Debt Model](concepts/triple-debt-model.md)
- [Vibe Coding](concepts/vibe-coding.md)
- [YAML](concepts/yaml.md)

## patterns (18)

- [Adversarial Code Review](patterns/adversarial-code-review.md)
- [Agent Constitution](patterns/agent-constitution.md)
- [Agent Optimization Loop](patterns/agent-optimization-loop.md)
- [Agentic Double Diamond](patterns/agentic-double-diamond.md)
- [Artifact Import](patterns/artifact-import.md)
- [The Compound Loop](patterns/compound-loop.md)
- [Constitutional Review](patterns/constitutional-review.md)
- [Context Gates](patterns/context-gates.md)
- [Context Map](patterns/context-map.md)
- [Experience Modeling](patterns/experience-modeling.md)
- [External Attention](patterns/external-attention.md)
- [Model Routing](patterns/model-routing.md)
- [Product Vision](patterns/product-vision.md)
- [Ralph Loop](patterns/ralph-loop.md)
- [Spec Reversing](patterns/spec-reversing.md)
- [The ADR](patterns/the-adr.md)
- [The PBI](patterns/the-pbi.md)
- [Specs](patterns/the-spec.md)

## practices (14)

- [ADR Authoring](practices/adr-authoring.md)
- [Adversarial Code Review](practices/adversarial-code-review.md)
- [Adversarial Requirement Review](practices/adversarial-requirement-review.md)
- [Agent Personas](practices/agent-personas.md)
- [AGENTS.md Specification](practices/agents-md-spec.md)
- [Constitutional Review Implementation](practices/constitutional-review-implementation.md)
- [Context Mapping](practices/context-mapping.md)
- [Context Offloading](practices/context-offloading.md)
- [Feature Assembly](practices/feature-assembly.md)
- [Living Specs](practices/living-specs.md)
- [Micro-Commits](practices/micro-commits.md)
- [PBI Authoring](practices/pbi-authoring.md)
- [Product Vision Authoring](practices/product-vision-authoring.md)
- [Workflow as Code](practices/workflow-as-code.md)

## recipes (3)

- [Adversarial Code Review](recipes/critic.md)
- [Spec Engineer](recipes/spec-engineer.md)
- [Write an AGENTS.md File](recipes/write-agents-md.md)

## resources (1)

- [Legend & Taxonomy](resources/legend.md)
