# Property-analysis publication contract

Dated private-property research in this directory is published automatically by
the GitHub Pages build. Add one Markdown file; do not hand-edit the report
catalog, landing-page cards or project-finder routes.

Use a direct child file named:

```text
YYYY-MM-DD-project-slug.md
```

It must begin with this exact structure:

```markdown
# Project name — short analysis description

Research captured: **YYYY-MM-DD HH:MM:SS SGT (UTC+08:00)**  
Property: **Project name, address, Singapore**  
Analysis type: **property resale inventory, valuation and investment analysis**  
Status: **point-in-time market snapshot**

## Decision

Lead with a concise evidence-based decision.
```

The date in `Research captured` must match the filename. A `Summary` metadata
line may be added after `Status`; otherwise the first Decision paragraph is
used for the library card and page description.

For a GLS site or another development that is not yet resale stock, add:

```markdown
Market stage: **future project**
```

Resale is the default market stage when this optional line is absent.

Publication rules:

- Keep advertised inventory, achieved transactions and scenario assumptions
  visibly separate.
- Preserve the research timestamp and link claims to dated public sources.
- For a future project, keep the official name, launch price, unit mix and TOP
  as TBA until announced; do not fabricate live inventory, caveats or rents.
- Use `##` and `###` headings below the single title.
- Use HTTP(S), email or in-page links only. Raw HTML, embedded media, relative
  links and executable URL schemes are rejected during the build.
- A newer report for the same project becomes the home-page and finder target.
  Every dated report keeps its permanent URL and catalog entry.
- Prefix a non-publishable working file with `_`, or keep it outside this
  directory.

Merging a valid report to `main` triggers the Pages workflow. The validated
static artifact is then deployed to
`https://evancjx.github.io/housing-estate-framework/`.
