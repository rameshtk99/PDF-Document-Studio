using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Core.Layout;

/// <summary>
/// The single shared footer-placement algorithm, consumed identically by the export pipeline and
/// the on-screen preview. Pure math: given how much blank space exists below a page's content and
/// how tall the footer table actually is (from <see cref="FooterTableLayout"/>), decides where the
/// footer goes and whether page content needs to be compressed to make room.
/// </summary>
public static class FooterLayoutCalculator
{
    /// <summary>Breathing room between the footer's top edge and the content's last ink.</summary>
    public const double SafetyGapPt = 6.0;

    /// <summary>Minimum distance from the footer's lower edge to the page's physical bottom edge.</summary>
    public const double FooterPhysicalMarginPt = 18.0;

    public readonly record struct Placement(
        /// <summary>Physical distance, in PDF points, from the page's bottom edge to place the footer at.</summary>
        double BottomMarginPt,
        /// <summary>True if the page's own content was scaled down to make room for the footer.</summary>
        bool ContentCompressed,
        /// <summary>Vertical scale factor applied to page content (1.0 if not compressed).</summary>
        double ContentScaleY,
        /// <summary>Vertical translation applied alongside the scale, anchored at the page top.</summary>
        double ContentTranslateY,
        /// <summary>True if the footer could not be placed without overlapping content (either
        /// because compression is disabled, or because the footer alone is taller than the page).</summary>
        bool OverlapsContent);

    public static Placement Compute(double pageHeightPt, double contentBottomFraction, double footerTableHeightPt, FooterConfig footer)
    {
        var requiredHeight = RequiredFooterFootprintPt(footerTableHeightPt, footer);
        var availablePts = contentBottomFraction * pageHeightPt;
        var deficit = requiredHeight - availablePts;

        if (deficit <= 0)
        {
            var margin = ComputeContentRelativeBottomMargin(pageHeightPt, contentBottomFraction, footerTableHeightPt, footer);
            return new Placement(margin, false, 1.0, 0.0, false);
        }

        if (!footer.CompressContent)
        {
            var margin = ComputeContentRelativeBottomMargin(pageHeightPt, contentBottomFraction, footerTableHeightPt, footer);
            return new Placement(margin, false, 1.0, 0.0, true);
        }

        var scaleY = (pageHeightPt - requiredHeight) / (pageHeightPt - availablePts);
        if (scaleY <= 0)
        {
            // Footer alone is taller than the page — nothing sane to compress to. Leave content
            // untouched and let the footer overlap rather than producing a degenerate transform.
            return new Placement(FooterPhysicalMarginPt, false, 1.0, 0.0, true);
        }

        var translateY = pageHeightPt * (1 - scaleY);
        return new Placement(FooterPhysicalMarginPt, true, scaleY, translateY, false);
    }

    /// <summary>Footer position when there's already enough natural whitespace: float just below
    /// the content (never closer to the page edge than <see cref="FooterPhysicalMarginPt"/>).</summary>
    public static double ComputeContentRelativeBottomMargin(double pageHeightPt, double contentBottomFraction, double footerTableHeightPt, FooterConfig footer)
    {
        var contentBottomPt = pageHeightPt * contentBottomFraction;
        var requiredHeight = RequiredFooterFootprintPt(footerTableHeightPt, footer);
        return contentBottomPt < requiredHeight
            ? FooterPhysicalMarginPt
            : FooterPhysicalMarginPt + (contentBottomPt - requiredHeight);
    }

    private static double RequiredFooterFootprintPt(double footerTableHeightPt, FooterConfig footer) =>
        footer.ContentGapPt + footerTableHeightPt + SafetyGapPt + FooterPhysicalMarginPt;
}
