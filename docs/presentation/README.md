# Pitch deck: Automated Vehicle Recovery Desk

Source for the 18-slide, 5-minute pitch deck (with the business case). One HTML file per slide in `slides/`, the slide order and
sections in `deck.json`, and the speaker plan with the marking-scheme mapping in `pitch-outline.md`.

- **Viewing:** the deck was built as a Claude "Slides" artifact (private link held by the author). These files are its source: each
  slide is a 1920x1080 `<section>` using that slide format's custom elements (`x-icon`, `x-shape`, `x-connector`), so a plain browser
  will not render them correctly. Import them into a Slides artifact, or ask the author for a PDF export.
- **Placeholders:** the revenue-model and market slides contain bracketed figures such as `[£__]`. Fill them from `market/MARKET.md`
  (branch `sim`) and `docs/` business case; do not add unsourced market numbers.
- **Positioning:** this version is UK-first. Project decision #32 says US-first, with the UK when the Automated Vehicles Act 2024
  regime is live; the business-case slides need updating to match.
- **Wording rules (#32):** say "recovery case" and "triage evidence"; do not call a named company "liable" or "defective"; quote
  careful drivers A and B together; no "self-driving" for unauthorised vehicles.
