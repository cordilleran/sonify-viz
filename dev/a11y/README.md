# Accessibility audit scripts

Reproduce the findings in `dev/reports/a11y-audit-260930.md`. They test the three standalone pages served from this repository; they do not build the Quarto site.

```bash
cd dev/a11y
npm init -y && npm i playwright-core axe-core     # versions used: 1.63.0 and 4.13.0
export CHROME=/path/to/chromium                    # default: /opt/pw-browsers/chromium
node server.js &                                    # static server with HTTP range support, port 8765
node axe.js      # axe-core at 1280 and 390 px; writes axe-results.json
node walk.js     # keyboard tab order, reflow at 640 and 320 px, forced-colours screenshots
node probe.js    # contrast pairs, slider values, canvas labels
node tree.js     # accessibility tree of the Superior Ice page and its live regions
```

Outputs are written to the current folder (`axe-results.json`, `*_forced.png`, `si_region.png`); do not commit the screenshots.

Limits: no screen reader was used. "Announced" claims come from the accessibility tree.
