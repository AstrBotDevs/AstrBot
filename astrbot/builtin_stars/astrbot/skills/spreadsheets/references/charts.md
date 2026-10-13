# Spreadsheet charts

Create a chart only when it makes a comparison, trend, distribution, ranking, progress measure, or relationship easier to understand.

## Select a chart

- Use bars or columns for category comparison and ranking.
- Use lines for trends over time.
- Use scatter plots for relationships between numeric variables.
- Use a histogram for a distribution when supported by the target viewer.
- Use pie or doughnut charts only for a small number of meaningful parts of one whole.
- Use a compact table when exact values matter more than visual pattern.

## Build auditable chart data

- Link series and categories directly to worksheet cells.
- Use a formula-backed helper range only when reshaping, grouping dates, or shortening labels is necessary.
- Keep unknown values blank rather than inventing zeroes.
- Verify headers are not included as numeric points.
- Keep category and value ranges the same length.
- Use a text helper label such as `2026-08` when date-axis rendering is unreliable.

## Format and place

- Give each chart one clear takeaway and include units in the title or axis.
- Use restrained, consistent colors and avoid gradients, 3D effects, and heavy borders.
- Keep labels, ticks, legends, and titles readable at normal zoom.
- Place charts beside or below the data they explain with blank gutters around them.
- Do not cover cells, controls, notes, or other charts.
- Set explicit axis number formats for currency, percentages, and dates.

After saving, reopen the workbook and inspect chart series formulas. Render the sheet and check for blank charts, clipped labels, stale ranges, wrong orientation, unreadable legends, and excessive whitespace.
