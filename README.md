# pfig (**p**aper **fig**ures)

This is a small, opinionated library to facilitate the disciplined development and export of publication-ready figures using `matplotlib` and `polars`.

**Disclaimer**: I am writing this for my own use; for now, expect API breakage with no support commitment.

- **Decoupled computation and rendering.**
  - Code that _prepares a figure's data_ is kept distinct from _code that turns this data into beautiful visuals_.
  - This is especially useful when a figure's code is computation-heavy. Don't rerun expensive data processing if you're just tweaking the style!
- **Rich metadata support.**
  - In user code, keep track of the parameters used to produce a figure in a disciplined manner.
  - Automatically benefit from tracking of additional metadata: git commit, export datetime, hostname...
- **Full history tracking.**
  - Don't accidentally overwrite valuable data.
  - Each figure export results in the creation of a separate directory.
- **Validation and safety.**
  - Directory names use readable formats without shell-problematic characters.
  - Automatic validation ensures directory names match their metadata contents.
