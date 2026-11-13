-- GitHub's Markdown renderer does not emit percentage-based column widths.
-- Remove Pandoc's inferred colspecs so wide tables retain their natural width
-- and scroll horizontally under the GitHub Markdown stylesheet.
function Table(table)
  local colspecs = {}
  for index, colspec in ipairs(table.colspecs) do
    colspecs[index] = { colspec[1] }
  end
  table.colspecs = colspecs
  return pandoc.Div({ table }, pandoc.Attr("", { "table-scroll" }))
end
