# Citations

Sources behind the entries. Every line carries a note on what it is and what it supports. Entries in the atlas do not rely on these for their numbers; the numbers come from the repros.

## Failure taxonomies and benchmarks for agents

- Why Do Multi-Agent LLM Systems Fail? (Cemri et al., 2025), https://arxiv.org/abs/2503.13657 - annotated failure traces from multi-agent frameworks grouped into specification, inter-agent misalignment, and verification failures; closest published relative of this atlas.
- tau-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains (Yao et al., 2024), https://arxiv.org/abs/2406.12045 - introduces pass^k, showing agents that succeed once often fail the same task on repeat; motivates the frequency ratings.
- ReAct: Synergizing Reasoning and Acting in Language Models (Yao et al., 2022), https://arxiv.org/abs/2210.03629 - the thought-action-observation loop whose missing progress check is PLAN-01.
- SWE-bench: Can Language Models Resolve Real-World GitHub Issues? (Jimenez et al., 2023), https://arxiv.org/abs/2310.06770 - the test-based benchmark that made VERIFY-02 style test gaming visible.
- Building effective agents (Anthropic, 2024), https://www.anthropic.com/research/building-effective-agents - practical argument for simple loops and explicit stopping conditions; context for the PLAN entries.

## Context

- Lost in the Middle: How Language Models Use Long Contexts (Liu et al., 2023), https://arxiv.org/abs/2307.03172 - measured U-shaped accuracy over the position of the relevant passage; the effect modelled in CTX-01.
- LLMs Get Lost In Multi-Turn Conversation (Laban et al., 2025), https://arxiv.org/abs/2505.06120 - shows models failing when the same task is spread over turns rather than given at once; relevant to CTX-02, CTX-04, CTX-06.
- Context Rot: How Increasing Input Tokens Impacts LLM Performance (Chroma, 2025), https://www.trychroma.com/research/context-rot - measures degradation as input length grows even on simple tasks; relevant to CTX-03 and CTX-04.
- Effective context engineering for AI agents (Anthropic, 2025), https://www.anthropic.com/research/effective-context-engineering-for-ai-agents - describes compaction, tool-result clearing, and just-in-time retrieval; the fixes in CTX-02 and CTX-04.
- Context Engineering for AI Agents: Lessons from Building Manus (Manus, 2025), https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus - production account of KV-cache hit rate as the metric that matters and of append-only, stable-prefix contexts; the basis of COST-02.

## Memory and retrieval

- PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models (Zou et al., 2024), https://arxiv.org/abs/2402.07867 - a handful of crafted documents can steer retrieval-augmented answers; the attack side of MEM-02.
- AgentPoison: Red-teaming LLM Agents via Poisoning Memory or Knowledge Bases (Chen et al., 2024), https://arxiv.org/abs/2407.12784 - backdoors planted in an agent's memory or knowledge base trigger on specific queries; relevant to MEM-02 and MEM-03.

## Tools, retries, and distributed-systems precedents

- Designing robust and predictable APIs with idempotency (Stripe, 2017), https://stripe.com/blog/idempotency - the canonical write-up of idempotency keys; the fix in TOOL-04 and TOOL-05.
- Timeouts, retries, and backoff with jitter (Amazon Builders' Library), https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/ - why retries amplify load and why jitter and limited retry layers matter; the basis of OPS-03.
- Addressing Cascading Failures, in Site Reliability Engineering (Google), https://sre.google/sre-book/addressing-cascading-failures/ - retry amplification, retry budgets, and load shedding; OPS-03 and OPS-02.
- The Confused Deputy (or why capabilities might have been invented) (Hardy, 1988), https://dl.acm.org/doi/10.1145/54289.871709 - the original statement of the confused deputy problem; SEC-02 is its agent-era instance.

## Security

- Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection (Greshake et al., 2023), https://arxiv.org/abs/2302.12173 - the paper that named indirect prompt injection through retrieved content; SEC-01.
- AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents (Debenedetti et al., 2024), https://arxiv.org/abs/2406.13352 - benchmark showing injection success against tool-using agents and the limits of prompt-level defenses; SEC-01.
- Design Patterns for Securing LLM Agents against Prompt Injections (Beurer-Kellner et al., 2025), https://arxiv.org/abs/2506.08837 - plan-then-execute, dual LLM, and context-minimization patterns; the structural fixes in SEC-01.
- Defeating Prompt Injections by Design (Debenedetti et al., 2025), https://arxiv.org/abs/2503.18813 - CaMeL separates control flow from untrusted data and tracks capabilities on values; the strongest version of the SEC-01 fix.
- The lethal trifecta for AI agents (Willison, 2025), https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ - private data, untrusted content, and an exfiltration channel together make an agent exploitable; frames SEC-01 and SEC-04.
- The Dual LLM pattern for building AI assistants that can resist prompt injection (Willison, 2023), https://simonwillison.net/2023/Apr/25/dual-llm-pattern/ - early statement of the privileged and quarantined model split; SEC-01.
- Bing Chat: Data Exfiltration Exploit Explained (Rehberger, 2023), https://embracethered.com/blog/posts/2023/bing-chat-data-exfiltration-poc-and-fix/ - data leaving through attacker-controlled links rendered in a chat answer; the channel in SEC-04.
- GitHub MCP Exploited: Accessing private repositories via MCP (Invariant Labs, 2025), https://invariantlabs.ai/blog/mcp-github-vulnerability - a malicious public issue steering an agent with broad token scope into leaking private repository content; SEC-01, SEC-02, TOOL-06.
- CVE-2025-32711, M365 Copilot information disclosure (Microsoft Security Response Center, 2025), https://msrc.microsoft.com/update-guide/en-US/vulnerability/CVE-2025-32711 - a zero-click data disclosure through content an assistant processed; SEC-01 and SEC-04 in a shipped product.
- Security Update for Amazon Q Developer Extension for Visual Studio Code (AWS Security Bulletin AWS-2025-015), https://aws.amazon.com/security/security-bulletins/AWS-2025-015/ - a malicious prompt shipped inside a released coding-assistant extension; SEC-01 arriving through a software supply chain instead of a web page.

## Verification and evaluation

- Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena (Zheng et al., 2023), https://arxiv.org/abs/2306.05685 - documents position bias, verbosity bias, and self-enhancement bias in LLM judges; VERIFY-04 and VERIFY-05.
- Large Language Models are not Fair Evaluators (Wang et al., 2023), https://arxiv.org/abs/2305.17926 - shows that swapping answer order flips judge verdicts and proposes calibration by order swapping; the fix in VERIFY-04.
- LLM Evaluators Recognize and Favor Their Own Generations (Panickssery et al., 2024), https://arxiv.org/abs/2404.13076 - self-preference in judges grows with self-recognition; relevant to VERIFY-01.
- Large Language Models Cannot Self-Correct Reasoning Yet (Huang et al., 2023), https://arxiv.org/abs/2310.01798 - self-correction without external feedback often does not help and can hurt; VERIFY-01.
- Length-Controlled AlpacaEval: A Simple Way to Debias Automatic Evaluators (Dubois et al., 2024), https://arxiv.org/abs/2404.04475 - regression-based removal of the length preference in automatic win rates; the fix in VERIFY-05.
- Proving Test Set Contamination in Black Box Language Models (Oren et al., 2023), https://arxiv.org/abs/2310.17623 - statistical test for benchmark items memorized by a model; the detection side of VERIFY-03.
- Recent Frontier Models Are Reward Hacking (METR, 2025), https://metr.org/blog/2025-06-05-recent-reward-hacking/ - documented cases of models special-casing graders and tests to score well; VERIFY-02.

## Public incidents and rulings

- Vibe coding service Replit deleted production database (The Register, 2025), https://www.theregister.com/software/2025/07/21/vibe-coding-service-replit-deleted-production-database/719783 - press account of a coding agent destroying a production database during a code freeze; context for why destructive tools need gates outside the prompt (TOOL-06, SEC-01).
- Moffatt v. Air Canada, 2024 BCCRT 149 (British Columbia Civil Resolution Tribunal), https://www.canlii.org/en/bc/bccrt/doc/2024/2024bccrt149/2024bccrt149.html - a company held liable for what its support chatbot told a customer; the cost of unverified agent output behind VERIFY-01.
- A postmortem of three recent issues (Anthropic, 2025), https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues - a provider's own account of infrastructure bugs that degraded model quality for weeks and escaped evals; context for OPS-04 on silent behavior changes that your own evals may not catch.

## Provider documentation used for the economics entries

- Prompt caching (Anthropic documentation), https://platform.claude.com/docs/en/build-with-claude/prompt-caching - cache hits require an identical prefix up to the cache breakpoint; the mechanism in COST-02.
- Prompt caching (OpenAI documentation), https://developers.openai.com/api/docs/guides/prompt-caching - exact-prefix matching and the advice to place static content first; COST-02.
