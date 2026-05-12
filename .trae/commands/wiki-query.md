---
name: "wiki-query"
description: "Query the LLM Wiki and synthesize an answer"
Usage: /wiki-query $ARGUMENTS
---

Follow the Query Workflow defined in AGENTS.md:
1. Read wiki/index.md to identify the most relevant pages
2. Read those pages (up to ~10 most relevant)
3. Synthesize a thorough markdown answer with [[PageName]] wikilink citations
4. Include a ## Sources section at the end listing pages you drew from
5. Ask the user if they want the answer saved as wiki/syntheses/<slug>.md

If the wiki is empty, say so and suggest ingesting files first.
