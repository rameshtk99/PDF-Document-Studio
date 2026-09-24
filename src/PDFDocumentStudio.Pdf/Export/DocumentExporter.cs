using PDFDocumentStudio.Core.Interfaces;
using PDFDocumentStudio.Core.Layout;
using PDFDocumentStudio.Core.Model;
using PDFDocumentStudio.Core.TextLayout;
using PDFDocumentStudio.Pdf.Analysis;
using PdfSharp.Drawing;
using PdfSharp.Pdf;

namespace PDFDocumentStudio.Pdf.Export;

public sealed record ExportResult(
    IReadOnlyList<int> AdjustedPages,
    IReadOnlyList<string> Warnings,
    IReadOnlyList<string> PerPageNotes);

/// <summary>
/// Renders an <see cref="EditorDocument"/> to a real, editable-text PDF: for every page, composes
/// the original page content (scaled down first if the footer needs room that isn't already
/// blank), the footer, and every visible object in z-order. Text objects stay real vector PDF
/// text; only images are ever rasterized. See docs/LEGACY_FEATURE_INVENTORY.md §2-§3, §16.
/// </summary>
public sealed class DocumentExporter(WhiteSpaceDetector whiteSpaceDetector, IFontMetricsProvider fontMetrics)
{
    private readonly FooterTableLayout _footerTableLayout = new(fontMetrics);
    private readonly TextLayoutEngine _textLayoutEngine = new(fontMetrics);

    public ExportResult Export(EditorDocument document, string outputPath, CancellationToken ct = default)
    {
        var adjustedPages = new List<int>();
        var warnings = new List<string>();
        var notes = new List<string>();
        var openStreams = new List<Stream>();

        try
        {
            using var writer = new PdfDocument();
            var totalPages = document.PageCount;

            for (var i = 0; i < document.Pages.Count; i++)
            {
                ct.ThrowIfCancellationRequested();
                var displayPageNumber = i + 1;
                ExportPage(writer, document.Pages[i], displayPageNumber, totalPages,
                    document.GetPageConfig(displayPageNumber), adjustedPages, warnings, notes, openStreams);
            }

            writer.Save(outputPath);
        }
        finally
        {
            foreach (var s in openStreams) s.Dispose();
        }

        return new ExportResult(adjustedPages, warnings, notes);
    }

    private void ExportPage(
        PdfDocument writer, PageRef pageRef, int displayPageNumber, int totalPages, PageConfig config,
        List<int> adjustedPages, List<string> warnings, List<string> notes, List<Stream> openStreams)
    {
        var form = XPdfForm.FromFile(pageRef.SourcePath);
        form.PageIndex = pageRef.SourceIndex;
        var pageWidth = form.PointWidth;
        var pageHeight = form.PointHeight;

        var page = writer.AddPage();
        page.Width = XUnit.FromPoint(pageWidth);
        page.Height = XUnit.FromPoint(pageHeight);

        var gfx = XGraphics.FromPdfPage(page, XGraphicsPdfPageOptions.Append);

        var footer = config.FooterConfig;
        var hasFooterText = footer.Enabled && footer.Table.Rows.Count > 0 && footer.Table.Columns.Count > 0;
        FooterLayoutCalculator.Placement? placement = null;
        FooterTableLayoutResult? tableLayout = null;

        if (hasFooterText)
        {
            tableLayout = _footerTableLayout.Layout(pageWidth, footer, displayPageNumber, totalPages);
            var contentBottomFraction = whiteSpaceDetector.AnalyzeContentBottomFraction(pageRef.SourcePath, pageRef.SourceIndex);
            placement = FooterLayoutCalculator.Compute(pageHeight, contentBottomFraction, tableLayout.Value.TotalHeight, footer);

            if (placement.Value.ContentCompressed) adjustedPages.Add(displayPageNumber);
            if (placement.Value.OverlapsContent)
                warnings.Add($"Page {displayPageNumber}: footer may overlap page content.");
            notes.Add(placement.Value.ContentCompressed
                ? $"Page {displayPageNumber}: content scaled to make room for the footer."
                : $"Page {displayPageNumber}: footer placed in existing whitespace.");
        }

        // Compose the original page content, scaled down (anchored at the top) only if the footer
        // needs room. In PDFsharp's default top-left/Y-down space, "anchor at page top" is simply
        // a scale from the origin — no translate needed (see docs/LEGACY_FEATURE_INVENTORY.md §3
        // for the equivalent Y-up derivation this was checked against).
        gfx.Save();
        if (placement is { ContentCompressed: true } p) gfx.ScaleTransform(1, p.ContentScaleY);
        gfx.DrawImage(form, 0, 0, pageWidth, pageHeight);
        gfx.Restore();

        if (hasFooterText && placement is not null && tableLayout is not null)
        {
            DrawFooterTable(gfx, footer, tableLayout.Value, placement.Value.BottomMarginPt, pageHeight);
        }

        foreach (var obj in config.Objects.Where(o => o.Visible).OrderBy(o => o.ZIndex))
        {
            switch (obj)
            {
                case TextPageObject text:
                    DrawTextObject(gfx, text, pageHeight);
                    break;
                case ImagePageObject image:
                    DrawImageObject(gfx, image, pageHeight, warnings, displayPageNumber, openStreams);
                    break;
            }
        }
    }

    private void DrawFooterTable(XGraphics gfx, FooterConfig footer, FooterTableLayoutResult table, double bottomMarginPt, double pageHeight)
    {
        if (table.ColumnLefts.Count == 0) return;

        var font = new XFont(footer.FontName, footer.FontSize);
        var brush = XBrushes.Black;
        var tableTopWorld = bottomMarginPt + table.TotalHeight;
        var tableLeft = table.ColumnLefts[0];
        var tableRight = table.ColumnLefts[^1] + table.ColumnWidths[^1];

        foreach (var row in table.Rows)
        {
            var rowTopWorld = tableTopWorld - row.Top;
            foreach (var cell in row.Cells)
            {
                foreach (var line in cell.Text.Lines)
                {
                    if (line.Text.Length == 0) continue;
                    var worldX = cell.Left + line.X;
                    var worldBaselineY = rowTopWorld - line.BaselineFromTop;
                    gfx.DrawString(line.Text, font, brush, new XPoint(worldX, pageHeight - worldBaselineY));
                }
            }
        }

        if (footer.Table.ShowBorders)
        {
            var pen = new XPen(XColors.Black, 0.75);
            var tableBottomScreen = pageHeight - bottomMarginPt;
            var tableTopScreen = pageHeight - tableTopWorld;

            gfx.DrawRectangle(pen, tableLeft, tableTopScreen, tableRight - tableLeft, tableBottomScreen - tableTopScreen);

            var y = tableTopWorld;
            foreach (var row in table.Rows)
            {
                y -= row.Height;
                if (y > bottomMarginPt + 0.01)
                    gfx.DrawLine(pen, tableLeft, pageHeight - y, tableRight, pageHeight - y);
            }

            for (var i = 1; i < table.ColumnLefts.Count; i++)
            {
                var x = table.ColumnLefts[i];
                gfx.DrawLine(pen, x, tableTopScreen, x, tableBottomScreen);
            }
        }
    }

    private void DrawTextObject(XGraphics gfx, TextPageObject obj, double pageHeight)
    {
        var style = obj.Style.Normalized();
        if (style.Text.Length == 0) return;

        var layout = _textLayoutEngine.Layout(style, obj.Width);
        var font = new XFont(style.FontName, style.FontSize);
        var (r, g, b) = ParseHexColor(style.Color);
        var alpha = (int)Math.Round(Math.Clamp(obj.Opacity, 0, 100) / 100.0 * 255);
        var brush = new XSolidBrush(XColor.FromArgb(alpha, r, g, b));

        var pivotScreen = new XPoint(obj.X + obj.Width / 2.0, pageHeight - (obj.Y + obj.Height / 2.0));
        var topOfBox = obj.Y + obj.Height;

        gfx.Save();
        if (obj.Rotation != 0) gfx.RotateAtTransform(obj.Rotation, pivotScreen);

        foreach (var line in layout.Lines)
        {
            if (line.Text.Length == 0) continue;
            var worldX = obj.X + line.X;
            var worldBaselineY = topOfBox - line.BaselineFromTop;
            gfx.DrawString(line.Text, font, brush, new XPoint(worldX, pageHeight - worldBaselineY));
        }

        gfx.Restore();
    }

    private static void DrawImageObject(
        XGraphics gfx, ImagePageObject obj, double pageHeight, List<string> warnings, int displayPageNumber,
        List<Stream> openStreams)
    {
        if (!File.Exists(obj.ImagePath))
        {
            warnings.Add($"Page {displayPageNumber}: image '{obj.ImagePath}' was not found and was skipped.");
            return;
        }

        ImageObjectRasterizer.Placement placement;
        try
        {
            placement = ImageObjectRasterizer.Prepare(obj);
        }
        catch (Exception ex)
        {
            warnings.Add($"Page {displayPageNumber}: image '{obj.ImagePath}' could not be rendered ({ex.Message}) and was skipped.");
            return;
        }

        var stream = new MemoryStream(placement.PngBytes);
        openStreams.Add(stream);
        var image = XImage.FromStream(stream);

        var screenX = placement.X;
        var screenY = pageHeight - placement.Y - placement.Height;
        gfx.DrawImage(image, screenX, screenY, placement.Width, placement.Height);
    }

    private static (byte R, byte G, byte B) ParseHexColor(string hex)
    {
        var h = hex.TrimStart('#');
        return (Convert.ToByte(h[..2], 16), Convert.ToByte(h[2..4], 16), Convert.ToByte(h[4..6], 16));
    }
}
