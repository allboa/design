# Origin record, 2026-09-30

These files are the scoping material that started allonboard. They are
frozen as of 2026-09-30: do not edit them. Anything that changes a decision
made here goes in a decision record under `decisions/` instead.

| File | What it is | Original name |
| --- | --- | --- |
| `post.md` | Design post, "A mapview for modern R: Arrow in, any CRS out". Blog-style advice, including the upstream review ("Where lonboard and deck.gl-raster sit") | `A mapview for modern R Arrow in, any CRS out.md` |
| `charter.md` | Project charter: goals, roadmap, org and repos, agent rules, first issues | `Plan.md` |
| `probe/prep.py` | Python stand-in for the R side: builds GeoArrow tables, a pre-projected raster mesh and a scene for EPSG:3031 | `prep.py` |
| `probe/bundle.json` | Output of `prep.py`: the scene (version 0.0.1) plus base64 Arrow IPC blobs | `bundle.json` |
| `probe/template.html` | The polar view probe page (deck.gl, orthographic view). The bundle is injected at `__BUNDLE__` | `template.html` |

## Notes

- The post and charter were exported from documents that had embedded
  diagrams (the architecture figure and the roadmap). Those appear as
  `[embedded content: ...]` placeholders and were not recovered.
- The post links to the probe as a claude.ai artifact. To view it locally,
  build the page from the template and the bundle:

  ```sh
  cd probe
  python3 -c "open('probe.html','w').write(open('template.html').read().replace('__BUNDLE__', open('bundle.json').read()))"
  ```

  The page loads deck.gl from a CDN, so it needs a network connection.
- `prep.py` fetches Natural Earth 50m land and coastline from GitHub and
  needs numpy, pyarrow, pyproj and shapely.
- The scene in `probe/bundle.json` is the starting point for scene spec 0.1
  in [allboa/scenespec](https://github.com/allboa/scenespec).
