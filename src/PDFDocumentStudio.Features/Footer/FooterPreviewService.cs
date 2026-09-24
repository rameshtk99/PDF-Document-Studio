using PDFDocumentStudio.Core.Interfaces;
using PDFDocumentStudio.Core.Layout;
using PDFDocumentStudio.Core.Model;
using PDFDocumentStudio.Pdf.Analysis;

namespace PDFDocumentStudio.Features.Footer;

public readonly record struct FooterPreview(bool HasFooter, FooterLayoutCalculator.Placement Placement, FooterTableLayoutResult Table);

/// <summary>Computes footer placement for on-screen preview using the same math
/// <see cref="Pdf.Export.DocumentExporter"/> uses for export.</summary>
public sealed class FooterPreviewService(WhiteSpaceDetector whiteSpaceDetector, IFontMetricsProvider fontMetrics)
{
    private readonly FooterTableLayout _tableLayout = new(fontMetrics);

    public FooterPreview Compute(
        string sourcePath, int sourceIndex, double pageWidth, double pageHeight,
        FooterConfig footer, int pageNumber, int totalPages)
    {
        if (!footer.Enabled || footer.Table.Rows.Count == 0 || footer.Table.Columns.Count == 0)
            return new FooterPreview(false, default, default);

        var table = _tableLayout.Layout(pageWidth, footer, pageNumber, totalPages);
        var contentBottomFraction = whiteSpaceDetector.AnalyzeContentBottomFraction(sourcePath, sourceIndex);
        var placement = FooterLayoutCalculator.Compute(pageHeight, contentBottomFraction, table.TotalHeight, footer);
        return new FooterPreview(true, placement, table);
    }
}
