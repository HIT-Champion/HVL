---
name: "Signet Butter office workspace"
description: "A bright operational workspace with butter navigation and olive actions."
colors:
  action: "#555b3f"
  action-hover: "#42492e"
  focus: "#666d4c"
  focus-soft: "#e9ead8"
  sidebar: "#f2ebd4"
  sidebar-edge: "#e7dfc3"
  nav-hover: "#eae2c8"
  nav-active: "#fffdf5"
  nav-ink: "#424734"
  ground: "#faf9f4"
  surface: "#fff"
  ink: "#30342a"
  muted: "#666a59"
  edge: "#e2e2d6"
  field-edge: "#898a79"
  attention: "#f6eedc"
  attention-edge: "#d5c396"
  attention-divider: "#dfd3b7"
  row-hover: "#f7f8f1"
  overdue: "#a02727"
typography:
  wordmark:
    fontFamily: "Lora, Georgia, serif"
    fontSize: "31px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "-0.035em"
  headline:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Noto Sans", Arial, sans-serif'
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.025em"
  highlight-title:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Noto Sans", Arial, sans-serif'
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.45
  row-title:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Noto Sans", Arial, sans-serif'
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Noto Sans", Arial, sans-serif'
    fontSize: "14px"
    lineHeight: 1.5
  metadata:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Noto Sans", Arial, sans-serif'
    fontSize: "13px"
    lineHeight: 1.5
rounded:
  chip: "4px"
  control: "8px"
  panel: "12px"
spacing:
  sm: "8px"
  md: "12px"
  row: "16px"
  panel: "24px"
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.action-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "#363d2c"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-ghost:
    textColor: "#555b48"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  input:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
    height: "44px"
  navigation:
    textColor: "{colors.nav-ink}"
    rounded: "{rounded.control}"
    padding: "11px 13px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
  attention-card:
    backgroundColor: "{colors.attention}"
    rounded: "{rounded.panel}"
    padding: "22px 24px 0"
  chip:
    rounded: "{rounded.chip}"
    padding: "2px 8px"
---

# Design System: Signet Butter office workspace

## Overview

**Creative North Star: "Butter operational workspace"**

Butter places warm yellow navigation beside a bright work canvas and white content. Dark olive actions and clear sans-serif reading text keep the interface practical. Lora supplies a modest vintage cue through identity alone.

This records the implemented local Butter system selected by the user after the interactive reroll. It replaces the prior wine system. It describes the implemented source; selecting the direction does not imply acceptance of every resulting screen. Surface composition belongs in its surface brief.

**Key Characteristics:**

- Butter navigation, warm white canvas and olive actions.
- Lora identity with sans-serif document work.
- Readable titles, labelled deadlines and real business state.
- Flat surfaces distinguished by tone, thin boundaries and space.
- Collapsible navigation with deliberate, reducible motion.

## Colors

Warm yellow and olive give the workspace its character; white work surfaces preserve contrast.

### Primary

- **Olive action:** Primary buttons, task actions, links and the dashboard's main series. Hover deepens the olive.
- **Olive focus:** Visible keyboard focus and active field boundaries; the soft focus tone supports field outlines.

### Secondary

- **Butter navigation:** The sidebar material, with a subtle matching edge, darker hover fill and near-white active destination.
- **Attention paper:** A pale warm task group with a stronger ochre boundary and quieter internal dividers.
- **Overdue red:** Overdue deadline text and the late chart series; always accompanied by meaningful text.

### Neutral

- **Warm canvas and white surface:** Separate the shell from fields, task lists and cards.
- **Ink and muted ink:** Primary reading and supporting metadata respectively.
- **Structural edge and field edge:** Quiet content dividers and stronger interactive boundaries.
- **Row hover:** A restrained light olive-white response.

**The State Meaning Rule.** Status, urgency and deadline remain separate signals derived from business data; color accompanies labels.

## Typography

**Wordmark Font:** Lora, Georgia, serif.
**Body and Heading Font:** Segoe UI, system-ui, Apple system, Noto Sans, Arial, sans-serif. Authentication uses its shorter Segoe UI/system stack.

### Hierarchy

- **Wordmark:** The sidebar uses the wordmark token; collapsed navigation shows the initial. Public identity uses 28px, authentication identity 40px.
- **Headline:** The inbox uses the headline token, becoming 27px at the small-screen breakpoint. General office headings use 24px; authentication uses 28px, weight 500, reducing to 24px on small screens.
- **Highlighted title:** Attention tasks use the highlight-title token, reducing to 18px at 1200px and below.
- **Row title:** Normal task titles use the row-title token, wrap freely and have a 70ch maximum width. Section headings use 16px at weight 600.
- **Body:** Navigation, ordinary work and controls use the body scale. Small-screen inputs use 16px to preserve usability.
- **Metadata:** Task identity, task labels and deadline text use the metadata scale. Status/urgency chips retain compact 12px type.

**The Work Type Rule.** Reserve Lora for identity; use sans-serif for office headings and document work.

## Layout

Desktop uses a left sidebar grid track of 244px, collapsing to 92px. A 16px left inset produces sidebar panels of 228px and 76px. The panel is sticky, begins 16px from the top and spans viewport height minus 32px. Main workspace width is capped at 1380px, with 42px top and 56px horizontal padding. A quiet utility row precedes the work surface.

The shell collapses over 260ms using cubic-bezier(.16,1,.3,1); labels fade over 110ms. The preference persists under `signet.sidebar.collapsed`. Icons retain accessible names and collapsed title hints. Staff see four primary destinations; clerk, director and tenant administrator destinations remain role-driven. Search remains a sidebar utility; verification is in the footer.

At 1200px and below, workspace padding becomes 32px/28px and the date hides. At 900px and below, navigation becomes a 256px fixed drawer with 10px inset and a scrim; the content uses 20px/24px padding. Opening moves focus into navigation, traps Tab, makes the workspace inert and locks body scrolling. Closed mobile navigation is inert; Escape, scrim or navigation closes it and returns focus to the trigger. At 640px and below, horizontal padding becomes 18px, search occupies its own toolbar line and filters share the next line with refresh.

Incoming/outgoing document tables become labelled stacked rows on small screens. Register and audit tables retain a 1050px minimum width in focusable scroll regions, with a scrolling hint and sticky first column below 900px.

## Elevation & Depth

Panels and authentication are flat at rest. Tone, thin boundaries and spacing establish depth. The open mobile drawer alone uses a soft lateral shadow (`8px 0 30px #30342a14`) and a dark translucent scrim (`rgb(48 52 42 / .4)`).

## Shapes

Controls and navigation use gently rounded control corners; panels and the sidebar use the panel radius. Chips keep the compact chip radius. Authentication retains its existing 14px panel and 7px field/button corners. These exceptions describe implemented authentication rather than extending the office radius scale.

## Components

### Buttons

Olive primary actions use white text; hover deepens the fill. Secondary actions use white with a stone boundary, while ghost actions use muted olive text. Shared buttons have a 44px minimum height, 8px/14px padding and control corners. Disabled buttons use muted neutral fill and text. Pressing moves enabled buttons down 1px. Background, text and boundary transitions last 140ms.

### Inputs / Fields

White fields use the strong field edge and a 44px minimum height. Focus shifts the boundary to olive with a soft 2px outline. Inbox search has an offset olive focus outline; native category and deadline filters are at least 46px high. Small-screen fields use 16px text. Invalid fields retain red borders and explanatory text.

### Chips

Compact labelled chips retain actual business mappings. Urgency levels use amber, orange and red with a thin matching ring; quiet normal urgency is omitted. Overdue is labelled separately from urgency. Status chips retain their business meanings while brand-colored states use the olive family.

### Cards / Containers

White cards use a fine structural edge and panel corners. Attention uses warm paper with an ochre edge. Normal inbox rows share an enclosing white list with dividers. Error/retry, loading skeleton, empty and clear-filter states remain legible within the same visual system.

### Navigation

The sidebar uses 14px labels and inline stroked SVG icons. Hover darkens the butter fill; active links use near-white fill and stronger text. Account and logout sit below navigation. The collapse toggle has an explicit expanded state, persistent preference and an accessible name. Ctrl/Cmd K routes to global search.

### Document rows

Each task is one document link containing title, identity, actual work, labelled deadline and arrow. There are no nested buttons. Normal rows use a three-column identity/deadline/arrow grid; small screens place deadline below identity. Attention titles are larger and show explicit urgency/overdue labels, with task action and deadline along the bottom. The inbox grouping policy is surface-specific.

### Case selection

Case selectors are full-width, left-aligned buttons with 18px/16px padding, 16px titles, 13px metadata and thin row boundaries. Hover uses a light olive surface; selected rows use butter fill and an explicit pressed state.

### Focus and motion

Shared keyboard focus is a 2px olive outline with a 3px offset; row focus is inset by 4px. Hover moves the task arrow 2px. Filtering and realtime list updates use 140ms opacity/translation and 180ms repositioning transitions. Reduced-motion preferences remove animations, transition durations, smooth scrolling and spatial press/hover effects.

## Do's and Don'ts

### Do:

- **Do** preserve butter navigation, warm white surroundings and olive actions.
- **Do** reserve Lora for identity and use sans-serif for document work.
- **Do** preserve real state labels, readable titles and explicit deadlines.
- **Do** preserve accessible collapsed names, drawer focus behavior and reduced motion.
- **Do** adapt forms and tables consistently without changing business rules.

### Don't:

- **Don't** restore the superseded wine masthead or the rejected small-type three-pane inbox.
- **Don't** add invented records, counts, AI capabilities or document previews.
- **Don't** use large serif office headings.
- **Don't** impose the inbox's attention composition on every business screen.
