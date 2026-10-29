# Frontend overhaul — UI/UX verification

Date: 29 October 2026. Baseline: ui.html from the user-provided investigation-source.zip. Candidate: replacement ui.html in this package.

QA Read: responsive redesign and internal-consistency review of a document investigation web app. No Figma or external design specification was supplied. Risk: medium. PIXEL_STRICTNESS=3, A11Y_LEVEL=7 target, UX_CRITIQUE=7. The full AA audit is incomplete; this is not a WCAG certification.

The installed qa-ui-ux-tester skill guided consistency, state, responsive and accessibility checks. Design implementation is the assistant's work, not a capability claimed for the audit skill.

## Scope and evidence

Browser: headless Chromium 133.0.6943.0, controlled through Playwright. Tests intercept the same HTTP paths used by the real API and return synthetic document/investigation fixtures. No live provider requests were made.

The run contains 32 passing scenario checks, including one original-UI baseline capture. There were zero browser JavaScript errors. Screenshots and computed measurements were inspected internally. This package includes textual measurement summaries; original screenshots are not included.

Observed layout regressions during development were corrected: narrow navigation exceeded the 375px viewport by 20px; a long filename expanded the sidebar grid beyond its available width. The final rerun passed the viewport overflow assertions, including the long-filename case.

## Browser checks

| Area | Observed result |
|---|---|
| Connected initial state | Live-response-shaped corpus counts and document metadata rendered |
| Initial responsive layout | No horizontal page overflow at 375x812, 768x1024, 1280x800, 1920x1080, 320x800 and 640x800 |
| Result responsive layout | No horizontal page overflow at widths 375, 768, 1280, 1920 and 320 |
| Long content / Georgian filename | Filename rendered as text; no inserted img node; no page overflow at the tested widths |
| Composer examples | Populate editable question and update character count |
| Busy state | Repeated form submission produces one investigation request; submit is disabled while pending |
| Conflicting evidence | Two findings, exact quotes, citations, unresolved limitation and search query list render |
| Source reader | Cited text is highlighted; full uploaded document can be opened |
| PDF metadata | Page number supplied in the fixture appears in source metadata |
| Keyboard | Escape closes the source dialog and returns focus to the citation; delete dialog starts on Keep document; keyboard focus outline observed |
| Library search | Filtered and empty-filter states render |
| Unsupported upload | Rejected client-side without sending an upload request |
| Multi-file upload | Two selected files produce two separate multipart upload requests |
| Replacement | PUT request followed by refreshed version metadata |
| Deletion | Cancel leaves data unchanged; confirm sends DELETE and refreshes the list |
| Library sizes | Empty, one-item and 25-item fixtures render |
| 429 response | Actionable quota message; question and previous result preserved |
| 502 response | Previous evidence preserved and submission re-enabled |
| Insufficient response | Explicit insufficient status, empty-findings explanation and limitations |
| Offline signal | Error announcement and reconnect control; successful reconnect restores ready state |

These are frontend checks against mocks. They are not proof that real file extraction, mutation durability, provider responses or vector retrieval are correct.

## Component × module consistency

Measured at 1280px viewport using browser computed styles.

| Property | Investigate primary button | Document upload primary button | Result |
|---|---|---|---|
| Background | rgb(20, 101, 79) | rgb(20, 101, 79) | Identical |
| Text | rgb(255, 255, 255) | rgb(255, 255, 255) | Identical |
| Font size | 12px | 12px | Identical |
| Border radius | 8px | 8px | Identical |
| Padding | 10px 15px | 10px 15px | Identical |
| Minimum height | 42px | 42px | Identical |

Document action buttons, source citations and modal close buttons are documented compact variants, not primary-button variants. Their authored minimum heights are 35px, 32px and 38px respectively, exceeding the 24px AA minimum target dimension. A complete all-element target-spacing audit has not been performed.

## Calculated text contrast spot checks

Ratios computed with WCAG relative luminance for the specified opaque foreground/background pairs. These spot checks do not establish whole-page conformance.

| Use | Foreground | Background | Ratio |
|---|---|---|---:|
| Main text | #1c3036 | #ffffff | 13.77:1 |
| Muted text | #617176 | #ffffff | 5.08:1 |
| Primary button | #ffffff | #14654f | 6.99:1 |
| Sidebar muted text | #9bb3b5 | #152b32 | 6.68:1 |
| Conflict badge | #80500e | #fff2dc | 6.18:1 |
| Highlighted quote | #393116 | #f6e6ab | 10.35:1 |

## Implemented design suggestions

- Separate document administration from the investigation workspace.
- Keep evidence adjacent to findings and label uncited material accurately.
- Use a source reader with exact quote highlighting rather than an undifferentiated text modal.
- Preserve drafts and previous findings during errors, while labeling old results clearly.
- Make connection, progress, empty-library and provider-limit states explicit.
- Use one shared token system and responsive navigation.

These are redesign decisions, not claims of deviations from a nonexistent Figma specification.

## Remaining checks

- Real-backend browser acceptance on the user's machine.
- Safari/WebKit, Firefox, Edge and real iOS/Android devices.
- Native browser 200%/400% zoom. The 640px/320px reflow checks are not reported as native zoom tests.
- Full keyboard-only traversal, screen-reader checks with NVDA/VoiceOver, complete AA checklist and full contrast inventory.
- First-time user research, timing measurements and large real upload-library performance.
- Public-hosting security/authentication and backend availability.

## Local acceptance after installation

1. Confirm the library lists existing uploads and a source opens.
2. Ask the existing CHG-7391 conflict question; inspect both quoted records.
3. Upload a disposable TXT; replace it; inspect its increased version; delete it after confirming.
4. Inspect the interface in a narrow browser window and navigate source dialogs with keyboard/Escape.

Do not treat this frontend update as a new model-quality evaluation or completion of the deployment requirement.
