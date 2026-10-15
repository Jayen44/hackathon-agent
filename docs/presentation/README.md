# Pitch deck: Automated Vehicle Recovery Desk

Source for the 19-slide, 5-minute pitch deck (with the business case). One HTML file per slide in `slides/`, the slide order and
sections in `deck.json`, and the speaker plan with the marking-scheme mapping in `pitch-outline.md`.

- **Viewing:** the deck was built as a Claude "Slides" artifact (private link held by the author). These files are its source: each
  slide is a 1920x1080 `<section>` using that slide format's custom elements (`x-icon`, `x-shape`, `x-connector`), so a plain browser
  will not render them correctly. Import them into a Slides artifact, or ask the author for a PDF export.
- **Positioning (decision #32):** United States first, United Kingdom when the Automated Vehicles Act 2024 regime is live. Market and
  financial figures come from `market/MARKET.md` (branch `sim`, 43 sources); shares, prices and the three-year plan are labelled
  assumptions on the slides. The worked unit-economics example uses UK court costs because they are the sourced ones; a United States
  legal and cost model is not built yet, and the slides say so.
- **Wording rules (#32):** say "recovery case" and "triage evidence"; do not call a named company "liable" or "defective"; quote
  careful drivers A and B together; no "self-driving" for unauthorised vehicles.
