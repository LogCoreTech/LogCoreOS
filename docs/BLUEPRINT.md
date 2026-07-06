# BLUEPRINT.md — LogCoreTech: $10k/mo in 6 Months

Business + product scaling blueprint. Sequenced by **dependency order, not time**. The checklists here are mirrored in `docs/TASKS.md` (the working queue); this file holds the strategy, math, and reasoning behind them.

**Goal: $10k/month revenue + a real user base/following within 6 months.**

---

## Revenue math (why the plan is shaped this way)

| Stream | Market rate | Needed for $10k/mo |
|---|---|---|
| Automation-service retainers | $1,000–$3,500/mo per small-biz client + $500–$1,500 setup | **4–8 clients** ✅ realistic |
| Managed hosting | $30–$75/mo per instance (comparables: Vikunja Cloud €4/user, Elestio $11/mo) | ~150–900 subscribers ❌ not in 6 months from cold |

**Strategy: retainers are the revenue engine; managed hosting + open-source community is the compounding product play that runs behind it.**

## Owner constraints (confirmed 2026-07-06)

- **Time: ~20 hrs/week** (full-time electrician job, married, buying a house). Strictly sequenced — revenue phases outrank everything; nothing runs "in parallel" unless it's automated.
- **Budget: under $500 total** unless profit covers expenses. Standard LLC filing ($45), free tiers everywhere, one small VPS. Biggest variable cost is Anthropic API usage — passed through to clients in pricing.
- **Channels: Facebook/local is the anchor.** LinkedIn + Reddit only via write-once cross-posting (automated with LogCore's own n8n — which is itself a case study). YouTube deferred until time is bought back (channel already exists).
- **"Buy back time" milestone:** first retainer revenue funds expenses immediately; at ~$5k MRR, evaluate cutting job hours to accelerate.
- **House closing within ~1 month (may fall through, another soon after):** mortgage underwriting scrutinizes new accounts, credit pulls, and unsourced deposits. Phase 0 is split into "safe now" vs "after closing."
- **Land investor expects cheap/favor pricing:** he becomes a structured *pilot / design partner*, not a full-price client. He gets the full instance day one (owner's choice — faster feedback loop), so the Automation Inbox stays on the critical path.
- **Warm niches for clients #2–6:** real estate & property management (reuses the deal-flow workflow almost verbatim) and contractors & trades (electrician network).

## Market research findings (Reddit / competitor scan, 2026-07)

- Closest competitors: **Khoj** (YC-backed AI second brain), **HomeChart / HomeHub** (self-hosted family organizers), **Vikunja / Donetick** (tasks/chores), OpenClaw-style personal agents.
- **Persistent AI memory is the #1 most-requested feature** in personal-AI communities — LogCore already has it. This is the marketing wedge.
- **Local LLM support (Ollama)** is the #1 credibility feature for r/selfhosted — currently Phase 6 in the product roadmap; pulled forward here.
- No competitor combines: AI memory + tasks/calendar + business workspace + n8n automations. "AI-native business OS" positioning is open.
- Nobody in the family-organizer space has an AI layer; nobody in the AI-assistant space has household/team pools. Don't fight Khoj on "second brain" — win on "it runs your operations."
- AI automation agency pricing benchmarks: small-biz retainers $1,000–$3,500/mo; quick-win builds $500–$1,500 one-time; median SMB retainer $2,800–$7,000/mo.

---

## Phase 0 — Unblock Everything (split for the mortgage)

### 0a — Safe to do now (no credit pulls, no new financial accounts)

- [ ] Get Anthropic API key (console.anthropic.com; Haiku for demo cost control)
- [ ] Commit + push the pending uncommitted change sitting since the session-5 work
- [ ] **Write the pricing sheet with real numbers.** Recommended starting tiers (market-validated):
  - **Hosted** — $200–500 setup + $50–100/mo: managed LogCore instance, no custom work
  - **Automation** — $1,000–1,500 setup + $1,000–1,500/mo: instance + 2–3 custom n8n workflows + support
  - **Ops Partner** — $2,500 setup + $2,500–3,500/mo: ongoing builds, monitoring, priority changes
- [ ] Branded email via Cloudflare Email Routing (`hello@logcoretech.com`)
- [ ] Bitwarden vault for all business credentials
- [ ] 2FA on Cloudflare, GitHub, Hetzner, registrar (Stripe when it exists)
- [ ] Ask the loan officer one question: "Does filing an LLC or receiving small side-business income before closing affect my underwriting?" — the answer gates Phase 0b timing
- [ ] 15-min name check: USPTO trademark search + Google "LogCore" for conflicts before investing further in the brand

### 0b — After the house closes (or lender explicitly clears it)

- [ ] File Arkansas LLC — **standard $45 filing** (expedited $300 only if a full-price client's payment is literally waiting on it)
- [ ] Get EIN (irs.gov, free, 5 min)
- [ ] Open business bank account (after LLC + EIN)
- [ ] Set up Stripe (invoicing + payment links)
- [ ] Wave accounting connected to the business bank account
- [ ] Business credit card — **only after closing**, never during underwriting (hard credit pull)

*Interim invoicing:* if the pilot converts to paid before 0b is done, invoice as a sole proprietor (Wave free invoicing, paid to a separate personal savings account you don't touch) — small, documented amounts; nothing that needs sourcing explanations.

## Phase 1 — Pilot Client (land investor as design partner)

*He expects favor pricing — so structure it as a pilot, in writing, with an end date. He gets the full instance day one (faster feedback), you get everything a first client is actually worth: proof, polish, and referrals.*

- [ ] **Write the pilot agreement (one page):** discounted rate (e.g., free/token setup + $250–500/mo, or 60 days free then Automation-tier price) in exchange for: written testimonial, a publishable case study with real numbers, 2 warm referral introductions, and a 15-min feedback call weekly. Pilot converts to standard Automation tier at a named date — the discount has an expiration, or it becomes permanent by default
- [ ] Build **Automation Inbox** (workflows write structured results to Brain JSON; per-item actions: Interested / Pass / Offer Made / Closed; skip already-reviewed) — on the critical path since he gets the full app
- [ ] Build **land lead search & qualify workflow** (n8n: LandWatch/Land.com/county records → AI-qualify by price/acreage/zoning → Automation Inbox)
- [ ] Write client onboarding runbook (VPS provision → tunnel → Infisical → first login handoff) — write it *before* the deploy, not during
- [ ] Demo with his actual criteria loaded → get the pilot agreement signed
- [ ] Deploy his full instance following the runbook (validates the runbook)
- [ ] Run the weekly feedback loop — log every piece of feedback as TASKS.md items; his polish list IS the product roadmap for the vertical
- [ ] After 2–4 weeks of results: publish case study + collect the 2 referral intros (they're in the agreement — the ask isn't optional)
- [ ] At the pilot end date: convert him to paid Automation tier (or part ways amicably with the case study in hand)

## Phase 2 — Public Launch Surface (demo + repo, prerequisite for all growth)

*Ordered: legal pages → demo infra → repo polish → website. Reddit/HN traffic bounces off a bad first impression, and you only get one launch.*

- [ ] Privacy policy page on logcoretech.com (blocker — users put personal data in)
- [ ] Terms of service page
- [ ] New Cloudflare Tunnel token for demo → `demo.logcoretech.com`
- [ ] Provision Hetzner CX22 demo VPS (~€4.50/mo)
- [ ] Deploy full stack, open registration on
- [ ] Demo AI cost protection: Haiku model + per-user daily message cap in chat router (do the cap, not just the model swap — demo abuse is guaranteed)
- [ ] Daily demo reset script (cron wipe of non-admin Brains)
- [ ] Demo banner in UI ("data resets nightly")
- [ ] UptimeRobot on demo URL
- [ ] Off-site backups (Hetzner snapshots or object storage) for the demo VPS — same pattern goes into the client onboarding runbook; on-box `backup.sh` alone is not a backup
- [ ] README: 3+ screenshots + a 30-second GIF of the AI doing something with memory
- [ ] CONTRIBUTING.md + GitHub issue templates + GitHub Discussions toggle
- [ ] Tag GitHub Release v0.1.0 (also makes the built-in updater work — `GITHUB_REPO` slug is already wired)
- [ ] Website: business-first hero copy, "Try the Demo" CTA, OG preview image, waitlist form (Formspree), Cloudflare Analytics
- [ ] LinkedIn company page

## Phase 3 — Client Acquisition Engine (client #1 → clients #2–6)

*Depends on Phase 1 (proof) + Phase 2 (credible public surface). Two warm verticals, two productized offers. The pilot is discounted, so $10k/mo needs ~6 full-price clients beyond him (or his conversion).*

- [ ] **Vertical offer #1 — RE / property management:** "deal flow on autopilot" — the land-lead workflow re-skinned for wholesalers, agents, property managers (lead search, qualification, follow-up). Near-verbatim reuse of the pilot build
- [ ] **Vertical offer #2 — contractors & trades:** lead intake + quote follow-up + scheduling reminders, sold through the electrician network. Different workflow set, same platform + runbook
- [ ] Service agreement template (liability cap, data-handling terms, "async support, 24–48h response") — required before client #2 signs
- [ ] One-page offer PDF per vertical + one 15-min demo call script
- [ ] List 50 prospects: RE investors/property managers (Facebook groups, BiggerPockets, pilot's referrals) + contractors/GCs known by name
- [ ] Outreach cadence: 10 personal messages/week minimum, fits in ~2 hrs — track in LogCore's own Business workspace (dogfood + screenshot material)
- [ ] Publish the pilot case study on website + Facebook page (cross-post to LinkedIn)
- [ ] Collect the 2 referral intros from the pilot agreement — these are prospects #1 and #2
- [ ] Close clients #2–#3 **at full price** (the pilot discount was the pilot's; never repeat it) → refine runbook, raise prices if closing >50%
- [ ] Close clients #4–#6 → **$10k/mo checkpoint: ~6 full-price clients averaging $1,700/mo**
- [ ] Weekly revenue tracker: MRR, pipeline count, churn — review every week, adjust tier pricing

## Phase 4 — Community & Following (parallel track, starts once Phase 2 ships)

*20 hrs/week reality: this whole phase is write-once, cross-post-everywhere. Facebook is the only channel with live engagement; LinkedIn/Reddit get repurposed content. YouTube deferred until time is bought back.*

- [ ] Screen-recorded demo GIF/video (2–3 min, unedited screen capture is fine — no editing skills needed; the single biggest conversion asset)
- [ ] Facebook page announcement to existing followers (first, cheapest audience)
- [ ] **n8n cross-posting workflow**: write one post → auto-publish to Facebook page + LinkedIn (this is also a sellable case study: "I automated my own marketing with LogCore")
- [ ] Build-in-public cadence: 1 post/week on Facebook (cross-posted) — revenue milestones, feature ships, lessons
- [ ] Discord server, linked from README + website
- [ ] Reddit launch: r/selfhosted first (lead with data-ownership + AI memory + local-first, NOT the business pitch), then r/n8n, r/productivity, r/homelab — spaced out, each post tailored; budget one evening each
- [ ] Show HN post once Reddit feedback is folded in
- [ ] Respond to issues/Discussions/Discord within 24 hrs for the first 90 days (batch into one daily 30-min slot)
- [ ] Following checkpoint: 500+ GitHub stars, 100+ Discord members, waitlist growing weekly
- [ ] *Deferred until time bought back:* YouTube videos on the existing channel

## Phase 5 — Product Features That Unblock Scale

*Build only when a phase above demands it. Priority order from market research:*

1. [ ] **Ollama / local LLM support** (pull forward from roadmap Phase 6) — #1 r/selfhosted credibility feature; the AGPL + "bring your own model" story is what makes the Reddit launch land
2. [ ] **Automation Inbox generalization** — from land-leads-specific to any workflow writing reviewable results (this is the productized-service platform)
3. [ ] **Instance provisioning script** — one command: new VPS → tunnel → Infisical → configured instance (turns client onboarding from hours to minutes; prerequisite for scaling past ~5 clients)
4. [ ] **Importers**: Todoist / Notion / Obsidian → Brain ("import my digital life" — switching cost is the #1 adoption blocker for competitors' users)
5. [ ] **Stripe billing portal** for hosted plans (waitlist → self-serve paid signup)
6. [ ] **Monthly value report per client** — auto-generated from Automation Inbox data (leads found, actions taken, hours saved); the anti-churn tool and a sales asset
7. [ ] **Email digests** (notification block already designed in PROJECT.md — ntfy is a barrier for normal business users)
8. [ ] Existing backlog when they surface in sales calls: customizable dashboard widgets, Projects module, multi-day calendar events

## Phase 6 — Convert the Following into the Second Revenue Stream

*Depends on Phase 4 traction + Phase 5 items 3 & 5.*

- [ ] Launch hosted plans to the waitlist ($15–30/mo personal, $50+/mo business)
- [ ] "Hosted" tier added to website with self-serve Stripe checkout
- [ ] Convert demo users: post-signup email/banner → hosted plan or self-host guide
- [ ] At 5+ retainer clients: contract out routine instance maintenance; owner time goes to sales + product
- [ ] Revisit revenue mix: if hosting MRR > $1k/mo, invest in the funnel; if not, double down on retainers

---

## Success metrics (checkpoint gates, not dates)

| Gate | You know the phase worked when… |
|---|---|
| Phase 0 | You can legally invoice and accept payment |
| Phase 1 | First client paid setup + month 1; case study exists |
| Phase 2 | A stranger can go website → demo → waitlist without touching you |
| Phase 3 | MRR ≥ $10k across ~6 retainer clients |
| Phase 4 | 500 GitHub stars, 100 Discord members, inbound leads exist |
| Phase 5/6 | New client onboarding < 1 hr; hosting MRR growing without your time |

## Second-order factors (each has a home in a phase)

- **Project direction rule:** for 6 months, *revenue decides the roadmap*. Business/automation features get built; personal/family features only ship via community PRs or when a paying client needs them. One repo, two audiences — the direction rule prevents drift.
- **Service agreement before client #2** (Phase 3): one template with liability cap, data-handling terms, and response-time expectations. The pilot agreement covers client #1; never onboard a full-price client on a handshake.
- **Support expectations vs the day job** (Phase 3): can't answer during work hours — put "async support, 24–48h response" in the agreement from day one. Selling response times you can't deliver is the fastest way to churn.
- **Key-man risk — owner is an electrician:** an on-the-job injury stops the whole business. Mitigations already in the plan (runbooks, Bitwarden, provisioning script) are also the continuity plan — treat them as non-optional. E&O/cyber insurance (~$500–1k/yr) deferred until MRR covers it.
- **Scraping fragility** (Phase 1): LandWatch/Land.com can block scrapers or change structure; county records are the durable source. Contract promises "qualified leads," never a named source. Build the workflow with a fallback source from day one.
- **Retention mechanics** (Phase 5 feature): auto-generated **monthly value report** per client. Retainers churn when clients forget what they're paying for; this feature is the anti-churn tool AND a demo asset.
- **Off-site backups for client + demo instances** (Phase 2 / onboarding runbook): `backup.sh` writing to the same VPS is not a backup. A client-data-loss event ends the business's reputation.
- **OSS community vs agency tension** (Phase 4): r/selfhosted reacts badly to repos that feel like agency lead-gen. Keep the README/community story genuinely self-host-first (Ollama support helps); keep the business pitch on the website.
- **Quarterly estimated taxes** (Phase 0b): once profitable, set aside 25–30% of business income; Wave tracks it, remit quarterly.

**Deferred deliberately (refine later, don't block):** entity structure beyond single-member LLC, insurance, hiring, paid ads, SOC2-style compliance questions, multi-tenant architecture. None of these matter before ~$5k MRR.

## Risks worth naming

- **AGPL + open source**: anyone can self-host free. That's fine — the retainer business sells *outcomes and operations*, not software. Don't get dragged into license anxiety.
- **20 hrs/week is the hard constraint**: Phases 1–3 (revenue) always outrank Phase 4–5 work when time conflicts. A week of only outreach and client delivery is a successful week.
- **House purchase + day job**: keep business cash strictly separate — lenders scrutinize deposits during underwriting; clean books matter more than usual right now.
- **Demo cost blowout**: the message cap is non-negotiable before the Reddit post.
- **Anthropic API costs at client scale**: pass AI usage through at cost or cap per tier in contracts.

## Verification

This is a business plan — verification is the weekly revenue tracker (Phase 3) and the checkpoint gates above, reviewed weekly. The working task queue in `docs/TASKS.md` mirrors these phases; keep the two in sync (a task done there gets checked here at each gate review).
