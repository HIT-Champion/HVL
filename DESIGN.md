---
name: "Signet Butter office workspace"
description: "A bright operational workspace with butter navigation and olive actions."
colors:
  action: "#555b3f"
  action-hover: "#42492e"
  focus: "#666d4c"
  focus-soft: "#e9ead8"
  sidebar: "#eee3bc"
  sidebar-edge: "#e0d3a5"
  nav-hover: "#eae2c8"
  nav-active: "#fffdf5"
  nav-ink: "#424734"
  ground: "#f4f5f1"
  surface: "#fff"
  ink: "#202820"
  muted: "#515b50"
  edge: "#d9ddd4"
  field-edge: "#898a79"
  attention: "#fffdf6"
  attention-edge: "#cbb57a"
  attention-divider: "#dfd3b7"
  row-hover: "#f7f8f1"
  overdue: "#a02727"
typography:
  wordmark:
    fontFamily: "Be Vietnam Pro, Segoe UI, sans-serif"
    fontSize: "25px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.04em"
  headline:
    fontFamily: '"Be Vietnam Pro", "Segoe UI", system-ui, sans-serif'
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  highlight-title:
    fontFamily: '"Be Vietnam Pro", "Segoe UI", system-ui, sans-serif'
    fontSize: "19px"
    fontWeight: 600
    lineHeight: 1.5
  row-title:
    fontFamily: '"Be Vietnam Pro", "Segoe UI", system-ui, sans-serif'
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: '"Be Vietnam Pro", "Segoe UI", system-ui, sans-serif'
    fontSize: "16px"
    lineHeight: 1.5
  metadata:
    fontFamily: '"Be Vietnam Pro", "Segoe UI", system-ui, sans-serif'
    fontSize: "14px"
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
    padding: "20px 24px 0"
  chip:
    rounded: "{rounded.chip}"
    padding: "2px 8px"
---

# Design System: Signet Butter office workspace

## Overview

**Creative North Star: "Butter operational workspace"**

Butter places warm yellow navigation beside a bright work canvas and white content. Dark olive actions and clear sans-serif reading text keep the interface practical. The Liền mạch logo uses two looping strokes suggesting an S and continuity. Stronger ink and a neutral bright canvas clarify the reading surface.

This records the implemented Butter system selected after the interactive reroll and refined on 24/10/2026. The user chose moderately airy density that prioritizes reading individual tasks and selected the Liền mạch logo from three explored directions. This is a refinement of Butter. It replaces the prior wine system. It describes the implemented source; selecting the direction does not imply acceptance of every resulting screen. Surface composition belongs in its surface brief.

**Key Characteristics:**

- Butter navigation, warm white canvas and olive actions.
- Liền mạch S mark and a sans-serif wordmark with sans-serif document work.
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

**Wordmark Font:** Be Vietnam Pro, Segoe UI, sans-serif.
**Body and Heading Font:** Be Vietnam Pro, Segoe UI, system-ui, sans-serif. Four self-hosted weights (400, 500, 600, 700) use font-display: swap; the office disables synthesized font weights. Authentication uses the same supplied font family and weights.

### Hierarchy

- **Wordmark:** The sidebar pairs a 25px/700 wordmark with a 32px Liền mạch SVG mark; collapsed navigation retains the mark. Public identity uses 26px/700, authentication identity 28px/700 with a 28px mark inside a 44px Butter tile. Favicon uses the same strokes on butter.
- **Headline:** The inbox uses the headline token, becoming 27px at the small-screen breakpoint. General office headings use 24px; authentication uses 24px/700, reducing to 22px on small screens.
- **Highlighted title:** Attention tasks use the highlight-title token, reducing to 18px at 1200px and below.
- **Row title:** Normal task titles use the row-title token, wrap freely and have a 64ch maximum width. Section headings use 16px at weight 600.
- **Body:** Base body is 16px/1.5; navigation and ordinary controls use 14px. Small-screen inputs use 16px to preserve usability.
- **Metadata:** Task identity, task labels and deadline text use 14px; section counts and utility context use 13px. Status/urgency chips retain compact 12px type.

**The Work Type Rule.** Use Be Vietnam Pro for identity, headings and work. Weight, measure and proximity establish hierarchy.

## Layout

Desktop reserves a fixed 76px icon rail. The 244px sidebar is fixed flush to the left, top and bottom viewport edges, with square outer corners. A clip-path reveals the expanded navigation over the workspace without shifting the reading column. Pointer entry opens immediately; pointer exit waits 140ms before closing to tolerate small accidental exits. Focus within also opens the sidebar. The manual collapse control and stored collapse preference are removed.

The reveal lasts 320ms with cubic-bezier(.16,1,.3,1); labels fade and slide independently. Active and hover backgrounds scale from a 48px icon target into the full navigation row. Icons retain accessible names and collapsed title hints. Permitted destinations remain role-driven; search stays below primary navigation and verification in the footer.

Main workspace width caps at 1440px with 28px top and 40px horizontal padding. The inbox reading column caps at 1080px. At 1200px and below, workspace padding becomes 32px/28px and the date hides. At 900px and below, or on devices without hover, navigation becomes a flush 256px touch drawer with a scrim. Opening moves focus into navigation, traps Tab, makes the workspace inert and locks body scrolling. Closed mobile navigation is inert; Escape, scrim or navigation closes it and returns focus to the trigger. At 640px and below, horizontal padding becomes 18px, search occupies its own toolbar line and filters share the next line with refresh.

Incoming/outgoing document tables become labelled stacked rows on small screens. Register and audit tables retain a 1050px minimum width in focusable scroll regions, with a scrolling hint and sticky first column below 900px.

## Elevation & Depth

Panels and authentication are flat at rest. Tone, thin boundaries and spacing establish depth. The desktop reveal uses a lateral shadow (`12px 0 28px #30342a12`); the open mobile drawer uses a soft lateral shadow (`8px 0 30px #30342a14`) and a dark translucent scrim (`rgb(48 52 42 / .4)`).

## Shapes

Controls and navigation use gently rounded control corners; panels use the panel radius; the flush sidebar has square outer corners. Chips keep the compact chip radius. Authentication uses the same 12px panel and 8px field/button corners. Its logo tile uses 10px corners.

## Components

### Buttons

Olive primary actions use white text; hover deepens the fill. Secondary actions use white with a stone boundary, while ghost actions use muted olive text. Shared buttons have a 44px minimum height, 8px/14px padding and control corners. Disabled buttons use muted neutral fill and text. Pressing moves enabled buttons down 1px and scales them to .98. Control feedback lasts 160–180ms.

### Authentication and recovery

Keycloak inherits upstream templates and authentication behavior. The Signet stylesheet is `keycloak-theme/moc/login/resources/css/signet.css`; changing the filename from moc.css avoids stale browser CSS from earlier previews. Authentication uses a 480px maximum form, neutral ground, white panel, olive actions, sans headings and consistent focus feedback. Locale selection wraps on small screens. Username/password, OTP and invalid-credential states share this theme. Callback/retry and the application error page share Signet identity and recovery actions. Verification stays publicly accessible. Document compose and body rendering also use the shared sans family.

### Inputs / Fields

White fields use the strong field edge and a 44px minimum height. Focus shifts the boundary to olive with a soft 2px outline. Inbox search has an offset olive focus outline; native category and deadline filters are at least 46px high. Small-screen fields use 16px text. Invalid fields retain red borders and explanatory text.

### Chips

Compact labelled chips retain actual business mappings. Urgency levels use amber, orange and red with a thin matching ring; quiet normal urgency is omitted. Overdue is labelled separately from urgency. Status chips retain their business meanings while brand-colored states use the olive family.

### Cards / Containers

White cards use a fine structural edge and panel corners. Attention uses warm paper with an ochre edge. Normal inbox rows share an enclosing white list with dividers. Error/retry, loading skeleton, empty and clear-filter states remain legible within the same visual system.

### Navigation

The sidebar uses 14px labels and inline stroked SVG icons. Hover darkens the butter fill; active links use near-white fill and stronger text. Account and logout sit below navigation. The sidebar opens on hover and focus, while touch devices use the labelled menu trigger. Ctrl/Cmd K routes to global search.

### Document rows

Each task is one document link containing title, identity, actual work, labelled deadline and arrow. There are no nested buttons. Normal rows use 20px/24px padding and a three-column identity/deadline/arrow grid; small screens place deadline below identity. Attention titles use 19px/600, with 16px identity bottom spacing and 12px above the footer; they show explicit urgency/overdue labels, with task action and deadline along the bottom. The inbox grouping policy is surface-specific.

### Case selection

Case selectors are full-width, left-aligned buttons with 18px/16px padding, 16px titles, 13px metadata and thin row boundaries. Hover uses a light olive surface; selected rows use butter fill and an explicit pressed state.

### Focus and motion

Shared keyboard focus is a 2px olive outline with a 3px offset; row focus is inset by 4px. Sidebar reveal is the focal interaction. Supporting motion expresses actual state changes: route transitions enter over 180–260ms and exit over 100–120ms; task filters/reordering use 220–280ms entrances and 110–140ms exits; notification popovers use a top-right reveal over 160–240ms and faster exits; transient notices slide in and reposition over 200–300ms. The scrim fades. Task arrows move 4px on hover/focus; navigation icons move 2px on hover. There are no scroll reveals, looping decorative animations or new animation dependencies. Reduced-motion preferences remove animation, transition durations, smooth scrolling and spatial press/hover effects while preserving all state changes.

## Do's and Don'ts

### Do:

- **Do** preserve butter navigation, warm white surroundings and olive actions.
- **Do** use Be Vietnam Pro throughout identity and work and preserve the chosen Liền mạch mark.
- **Do** preserve real state labels, readable titles and explicit deadlines.
- **Do** preserve accessible collapsed names, drawer focus behavior and reduced motion.
- **Do** adapt forms and tables consistently without changing business rules.

### Don't:

- **Don't** restore the superseded wine masthead or the rejected small-type three-pane inbox.
- **Don't** add invented records, counts, AI capabilities or document previews.
- **Don't** use large serif office headings.
- **Don't** impose the inbox's attention composition on every business screen.
