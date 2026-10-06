# Unreleased

- WebUI onboarding now ends after four steps: usage notice, model setup, inline ChatUI, and messaging platform. Completing or skipping the platform step opens the welcome screen. Removed the plugin recommendations, computer-access step, and batch-application page, including their requests and state. Plugin installation remains under Plugins -> Plugin Marketplace; permissions remain under Config -> AI -> Capabilities -> Agent Computer Use.
- Replace the welcome logo rotation with separate shooting-star entrances from the lower left and upper right, fading trails, and a static final logo. Respect reduced-motion preferences.
- Limit the onboarding trial composer to text input and Send/Stop. Remove upload, model/configuration selection, and voice controls from the trial only; regular ChatUI keeps its controls.
- WebUI onboarding prefills existing model defaults and messaging adapters in editable forms instead of a status-only adapter list. Unchanged adapters proceed without writes; edits update the selected adapter without duplicating or automatically enabling it. Refined header and footer spacing, full-width advanced settings, a reduced-motion-aware welcome icon animation.


- WebUI: Extended initial account setup with the first-use notice, model configuration, unframed inline ChatUI testing, and platform adapters. The wider guide keeps bottom actions visible without installing plugins or changing computer-access permissions. Removed the standalone welcome page and sidebar item; legacy links and ordinary logins go to the dashboard. Reopen the guide from Settings -> Maintenance without resetting configuration.
- WebUI onboarding aligns content and the trial composer with the brand header, opens the trial session automatically, and reuses existing model and platform forms. First-step Set up later is renamed to Skip entire setup; step subtitles use concise configuration descriptions. Primary footer actions consistently read Next and include a forward arrow.
