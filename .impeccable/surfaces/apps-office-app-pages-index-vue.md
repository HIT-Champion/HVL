---
version: 1
slug: "apps-office-app-pages-index-vue"
primary_target: "apps/office/app/pages/index.vue"
related_targets: ["apps/office/app/layouts/default.vue", "apps/office/app/components/TaskQueueItem.vue", "apps/office/app/assets/css/main.css"]
---

# Signet — Butter workspace

Mode: Operate. Primary audience: daily document-processing staff. Existing roles, API contracts and permissions remain authoritative. The user explicitly selected **butter** after rerolling three interactive proposals on 23/10/2026. This replaces the rejected wine masthead and the earlier three-pane workbench. On 24/10/2026 the user chose moderately airy density that prioritizes individual tasks and selected the Liền mạch logo from three explored directions. These refine the selected Butter composition.

THESIS: Staff see actual tasks needing attention first and remaining work below, with one direct document link per item.

OWN-WORLD: Butter navigation, warm white surroundings, white work surfaces and olive actions. Gentle 8px controls and 12px panels. Self-hosted Be Vietnam Pro (400/500/600/700) carries identity and work. The Liền mạch mark uses two looping S strokes: 32px beside a 25px/700 sans wordmark, and mark alone when collapsed. Ground #f4f5f1, ink #202820, muted #515b50, sidebar #eee3bc and attention #fffdf6 with edge #cbb57a distinguish reading regions. Tokens belong to root DESIGN.md.

STORY: Enter assigned work; find urgent or overdue items; optionally filter by document type, deadline state or text; open the real processing page. Metadata, full files and business actions stay in document detail. No duplicate preview or invented history.

FIRST VIEWPORT: A76px icon rail expanding to244px on hover/keyboard focus with synchronized workspace reflow, a light utility row and one work axis. Main heading/compose, scoped search and native filters, attention surface, remaining list. Workspace caps at 1440px with 28px top/40px horizontal padding; the inbox caps at 1080px. Heading and toolbar spacing and task-group gaps use 24px. Normal titles use 17px/600 (attention 19px/600), 64ch maximum, with 14px metadata. Sidebar retracts to a fixed 76px icon rail, preserving accessible icon names without a stored collapse preference. Below 900px or on no-hover devices it becomes a focus-trapped drawer with inert background; phone content stacks deadlines beneath task titles.

FORM: seed:69aa3c2a0b521ac9, surface/operate reroll1. The three dealt compositions were4/2/5; Butter was candidate5 and selected directly in chat. The user's pinned left sidebar, bright vintage palette, mild rounding and motion supersede the old unapproved visual system. Code-led chosen reference: `.impeccable/mocks/decision/butter-attention.html`; screenshots in `.impeccable/review-v3/reroll-1/`.

FINISH: Compare live source and screenshots honestly. A chosen direction is not acceptance of the final implementation. Sidebar mask reveal320ms, task feedback110–280ms, reduced motion removes spatial effects. Real task urgency or overdue due_on determines attention; each task appears once. The original Butter handoff was local; this brief grants no publishing authorization. Preserve current user instructions on branches and publishing.

## Preserved functions and adaptations

- `myTasks`, notifications, deadline rollover, retry/empty recovery and direct document routes remain live.
- Category filtering joins the pre-existing all/today/overdue/urgent filter; no business state is invented.
- The drawer threshold is900px, or any no-hover device, with flush viewport edges and touch menu.
- Existing notification, language, logout and verification controls remain available; their presence is a functional adaptation to the prototype.
- The Butter system extends to forms, tables, cases and charts; their own information architecture is preserved.
