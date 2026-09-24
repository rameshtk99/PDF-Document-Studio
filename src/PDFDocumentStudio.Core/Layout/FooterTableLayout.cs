using PDFDocumentStudio.Core.Interfaces;
using PDFDocumentStudio.Core.Model;
using PDFDocumentStudio.Core.TextLayout;

namespace PDFDocumentStudio.Core.Layout;

/// <summary>One laid-out cell: its wrapped lines (from the shared <see cref="TextLayoutEngine"/>), position, and size.</summary>
public readonly record struct FooterTableCell(TextLayoutResult Text, double Left, double Width);

public readonly record struct FooterTableRowLayout(IReadOnlyList<FooterTableCell> Cells, double Top, double Height, bool IsHeader);

public readonly record struct FooterTableLayoutResult(
    IReadOnlyList<double> ColumnLefts, IReadOnlyList<double> ColumnWidths,
    IReadOnlyList<FooterTableRowLayout> Rows, double TotalHeight);

/// <summary>
/// The single shared footer table layout: column widths, {page}/{total} substitution, and
/// per-cell wrapping — consumed identically by preview and export. Cell text wrapping reuses
/// <see cref="TextLayoutEngine"/> rather than re-implementing it, so a footer cell wraps exactly
/// like any other text object.
/// </summary>
public sealed class FooterTableLayout(IFontMetricsProvider metrics)
{
    private readonly TextLayoutEngine _textLayout = new(metrics);

    public FooterTableLayoutResult Layout(double pageWidthPt, FooterConfig footer, int pageNumber, int totalPages)
    {
        var table = footer.Table;
        var columnCount = table.Columns.Count;
        if (columnCount == 0)
            return new FooterTableLayoutResult([], [], [], 0);

        var availWidth = Math.Max(1.0, pageWidthPt - footer.LeftMargin - footer.RightMargin);
        var explicitTotal = table.Columns.Where(c => c.WidthPt.HasValue).Sum(c => c.WidthPt!.Value);
        var autoCount = table.Columns.Count(c => !c.WidthPt.HasValue);
        var autoWidth = autoCount > 0 ? Math.Max(10.0, (availWidth - explicitTotal) / autoCount) : 0.0;

        var widths = table.Columns.Select(c => c.WidthPt ?? autoWidth).ToArray();
        var lefts = new double[columnCount];
        var x = footer.LeftMargin;
        for (var i = 0; i < columnCount; i++) { lefts[i] = x; x += widths[i]; }

        var rows = new List<FooterTableRowLayout>();
        var top = 0.0;

        if (table.ShowHeader)
        {
            var headerRow = BuildRow(table.Columns.Select(c => Substitute(c.Header, pageNumber, totalPages)).ToList(),
                table.Columns.Select(c => c.Align).ToList(), lefts, widths, footer, top, isHeader: true);
            rows.Add(headerRow);
            top += headerRow.Height;
        }

        foreach (var row in table.Rows)
        {
            var cellTexts = Enumerable.Range(0, columnCount)
                .Select(i => Substitute(i < row.Cells.Count ? row.Cells[i] : string.Empty, pageNumber, totalPages))
                .ToList();
            var laidOut = BuildRow(cellTexts, table.Columns.Select(c => c.Align).ToList(), lefts, widths, footer, top, isHeader: false);
            rows.Add(laidOut);
            top += laidOut.Height;
        }

        return new FooterTableLayoutResult(lefts, widths, rows, top);
    }

    private FooterTableRowLayout BuildRow(
        IReadOnlyList<string> cellTexts, IReadOnlyList<FooterCellAlign> aligns,
        IReadOnlyList<double> lefts, IReadOnlyList<double> widths, FooterConfig footer, double top, bool isHeader)
    {
        var cells = new List<FooterTableCell>(cellTexts.Count);
        for (var i = 0; i < cellTexts.Count; i++)
        {
            var style = new TextStyle
            {
                Text = cellTexts[i],
                FontName = footer.FontName,
                FontSize = footer.FontSize,
                AutoSize = false,
                Padding = footer.CellPaddingPt,
                Align = aligns[i] switch { FooterCellAlign.Left => TextAlign.Left, FooterCellAlign.Right => TextAlign.Right, _ => TextAlign.Center },
            };
            var text = _textLayout.Layout(style, widths[i]);
            cells.Add(new FooterTableCell(text, lefts[i], widths[i]));
        }

        var height = cells.Count > 0 ? cells.Max(c => c.Text.ContentHeight) : footer.FontSize + 2 * footer.CellPaddingPt;
        return new FooterTableRowLayout(cells, top, height, isHeader);
    }

    private static string Substitute(string text, int pageNumber, int totalPages) =>
        text.Replace("{page}", pageNumber.ToString()).Replace("{total}", totalPages.ToString());
}
