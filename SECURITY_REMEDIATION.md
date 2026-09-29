# Security remediation, 2026-09-28

Scope: current `main` tree based on `dce018e9e29192a432b56ddb17bfe36b26c2e668`.

| Finding | Change | Verification/status |
|---|---|---|
| Personal absolute paths in reference history | Replace 36 occurrences with anonymized source labels; explain that labels are historical provenance, not bundled assets | Current text scan; JSON parse |
| Review API arbitrary path access | Restrict manifests to public URLs on the exact viewer origin; reject traversal, other schemes/origins, symlinks; bound JSON input | Automated traversal/symlink/HTTP tests |
| Review output arbitrary overwrite | Require a relative dedicated `reviews` directory; JSON latest file directly inside it; exclusive archives and atomic latest replacement | Normal saves, concurrent archives, hard-link preservation tests |
| Cross-site access and network exposure | Loopback client and Host validation, exact Origin for POST, JSON-only POST, no CORS | Cross-origin/null/missing Origin, Host and non-loopback tests |
| Static public symlink disclosure | Validate public-file requests before Vite serves them; block raw `@fs` URLs; restrict Vite filesystem root | Middleware regression test and actual Vite checks |
| Viewer DOM XSS | Validate colors, escape tag kind, normalize tag kind; same-origin project-only assets; prototype-free lookup dictionaries | Injection URL/color unit tests, production builds |
| Installer deletion/overwrite | Remove rsync deletion; reject existing and symlink destinations; new-directory installation only | Sentinel preservation, repeat install rejection, normal install tests |
| Dependency vulnerabilities | js-yaml 4.3.2; Vite 7.3.6; esbuild 0.28.2; PostCSS 8.5.28; nanoid 3.3.19, regenerated locks | Both npm audits report 0 known vulnerabilities at execution time |
| Absolute-path diagnostic output | Filename-only blink-plan provenance, review CLI summaries, checklist summaries; project-relative API results; generic filesystem errors | Source review and API/installer output tests |
| PNG private metadata | Remove EXIF/text/XMP/time chunks without recompression in 7 PNGs; keep color profiles | All 68 PNGs inspected by the read-only GitHub CI job; 7 changed with exact decoded RGBA comparison locally; the first CI run found only the final 2 pending image updates |
| Future regressions | Read-only, SHA-pinned GitHub Actions workflow runs security tests, builds, dependency audits, and tracked-file privacy/PNG checks | First GitHub CI run: both review-tool jobs passed tests/builds/audits; privacy job identified only the final 2 image updates |

## Remaining publication gates

- Existing Git history still contains personal path data and personal author/committer email. A normal forward commit does not remove these objects. History rewriting and remote cache/fork cleanup are not complete.
- The connector does not expose branch-protection writes or author/committer/signing options. Branch protection and verified commit-signing policy are not configured by this change.
- Local PNG retrieval was limited to 36 files, but GitHub CI inspected all 68 files in the complete checkout. The first run identified only the final 2 image updates included in the follow-up commit. Confirm that the follow-up privacy job reports zero findings before publication.
- Browser fallback was denied. No browser access, credential changes, or protection bypass was used.

## Reproduce

Run `npm ci --ignore-scripts`, `npm test`, `npm run build`, and `npm audit --audit-level=low` inside each viewer template directory. Run `python3 -m unittest discover -s tests -v` and `python3 tools/security_check.py` from the repository root.

`tools/sanitize_png.py` checks named PNGs without modification by default. Use `--write` to remove text/EXIF/time chunks; it validates chunk CRCs and preserves image-data and color-profile chunks. It does not inspect information drawn into the pixels or claim to anonymize arbitrary ICC profiles.

The local-server protection assumes that other OS users/processes cannot mutate the workspace concurrently. Filesystem containment is not a sandbox against a hostile process with the same OS write permissions. The signature/branch-policy items are governance controls; their absence alone is not evidence of a code exploit. No audit can guarantee the absence of all undiscovered vulnerabilities.
