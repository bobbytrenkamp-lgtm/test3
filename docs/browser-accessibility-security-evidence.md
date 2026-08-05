# Browser accessibility and client-security evidence

Evidence date: 2026-08-04. Surface: Codex in-app Chromium browser against the exact local branch on `127.0.0.1`. Data: explicit fictional demo workspace and synthetic injection strings only. The viewport override was reset and every audit tab was closed after testing.

## Results

| Area | Evidence | Result |
|---|---|---|
| Authentication isolation | Signed-out state set `inert` and `aria-hidden=true` on skip link, top bar and workspace shell; password was empty and focus returned to email after sign-out | Pass |
| Semantic structure | Active view had one H1, no visible heading-level skip, no duplicate IDs, no missing image alt, no unnamed visible control and no target below 24 CSS px in the measured pipeline view | Pass |
| Keyboard upload | Document room exposed exactly one semantic `button "Upload document"`; activation delegates to the hidden native multi-file control | Pass |
| Mobile navigation | At 390×844, document width and scroll width were both 390, bottom navigation was 390×58 at the viewport bottom, nine nav actions were visible, and the 35×35 initials control exposed `Sign out Casey Analyst` | Pass |
| Text contrast | Computed-style audit of visible pipeline headings, paragraphs, labels, small text, controls and links found zero failures; lowest sampled ratio was 4.73:1 against a 4.5:1 requirement | Pass |
| Stored injection | Deal name `<img src=x onerror="globalThis.__test3xss=1"> Institutional` and a script-tag address rendered as literal text; the deal list contained zero injected `img` and zero injected `script` elements | Pass |
| Session revocation | Mobile sign-out returned to the sign-in heading, cleared the password, focused email and made all workspace roots inert/hidden; server-side replay denial is also covered by HTTP tests | Pass |
| Browser diagnostics | Warning/error log query returned an empty list | Pass |
| Responsive cache coherence | Versioned `styles.css` and `app.js` asset URLs loaded the audited revision after reload | Pass |

## Automated regression gate

`python scripts/accessibility_guard.py` runs in CI before dependency installation. It checks HTML language, duplicate IDs, label/reference/alt contracts, button naming, initial authentication isolation, skip/main/status landmarks, focus-visible CSS and reduced-motion CSS. Unit/live-HTTP tests remain separate because a static parser cannot prove runtime state transitions.

## Defects found and corrected during the browser run

1. Workspace navigation and destructive controls remained reachable behind the sign-in overlay. Initial inert/hidden contracts and runtime state transitions now isolate them.
2. The desktop sidebar sign-out disappeared at the compact breakpoint. The signed-in initials are now a labeled, always-visible sign-out button using the same revocation path.
3. `display:none` removed the upload input from keyboard/accessibility semantics. A semantic button now opens the hidden native chooser.
4. Metric helper text was 3.08:1 and the eyebrow rule lost to a more-specific paragraph rule. The muted token and explicit eyebrow rule now meet the sampled contrast requirement.
5. Styles could remain cached while HTML changed during a release. Core CSS/JS URLs now carry the application version.

## Limitations

This is a reproducible browser/DOM/computed-style audit, not certification. It does not replace testing with NVDA/JAWS/VoiceOver, high-contrast/forced-colors modes, 200–400% zoom, cognitive usability research or a complete WCAG 2.2 evaluation. The app remains explicitly not production-ready until the final requirement audit and remaining recovery/security limitations are closed or accurately deferred.
