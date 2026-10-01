# Agent brief for allboa

Every agent reads this before touching any repo in the
[allboa](https://github.com/allboa) org. It applies to humans too.

allonboard builds a map viewer for R that draws data in its own CRS, polar
views included, from GeoArrow and grid descriptors. The charter is
[`origin/2026-09-30/charter.md`](origin/2026-09-30/charter.md) and the design
post is [`origin/2026-09-30/post.md`](origin/2026-09-30/post.md). Decisions
made since then are in [`decisions/`](decisions/).

## Repos

| Repo | Scope |
| --- | --- |
| `design` | Origin record (frozen), decision records, this brief |
| `scenespec` | Scene spec JSON Schema, fixtures, validator, conformance scenes |
| `spikes` | Throwaway experiments; each ends in a decision record here |
| `aobcore` | Lean R core: producers to GeoArrow and grid descriptors, scene building, embed transport, bundled renderer (placeholder name) |
| `aobview` | `view(x)` for wk-handleable vectors (sf included) and terra, palettes, legends, popups (placeholder name) |

## Design principles

- **Primitives first, recipe not payload.** Prefer sending a URL or a
  descriptor over materialized data. Prefer thin composable functions over
  one large interface.
- **Lean dependencies.** Core Imports stay at nanoarrow, geoarrow, wk and
  htmltools. Anything else needs a decision record.
- **The scene spec is renderer-neutral.** No deck.gl names, props or concepts
  in the schema. A renderer implements the spec.
- **Native GeoArrow only** in the data plane. WKB is converted before it
  leaves R.
- **ASCII only** in package sources and shipped files. Any exception needs a
  stated reason in the PR.
- **Polar first.** Every rendering feature is tested in EPSG:3031 before Web
  Mercator.

## How work flows

1. Work starts from an issue with acceptance criteria. Comment on the issue
   to claim it.
2. One issue, one branch, one PR. The PR links the issue and says how each
   criterion was checked.
3. Rendering changes include a headless screenshot of the conformance
   scenes, light and dark.
4. A spike ends with a short decision record in `design/decisions/`, even
   when the answer is no. Start from
   [`decisions/0000-template.md`](decisions/0000-template.md).
5. Review and merge: every PR is reviewed by a separate agent against the
   charter, the design post and the decision records. When that review
   passes and CI is green, the agent that opened the PR merges it. main is
   protected and CI must pass. Michael is not a required reviewer (his
   decision, 2026-09-30, replacing the charter's required-reviewer rule);
   widening agent merge rights beyond this is gate C.
6. Stop and ask Michael before anything that changes the plan's goals or
   non-goals, before a gate decision (A: tiled-raster approach, B: proposing
   the scene spec to lonboard, C: widening agent merge rights), and before
   any step that cannot be undone (deleting a repo or branch history,
   posting outside the org, submitting to CRAN).
7. Agents act through the org's GitHub App, installed on this org only. No access to other orgs or
   personal repos.
