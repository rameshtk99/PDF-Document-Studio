namespace PDFDocumentStudio.Core.Model;

/// <summary>One (line1, line2) pair for a footer column.</summary>
public readonly record struct FooterColumn(string Line1, string Line2)
{
    public bool IsEmpty => string.IsNullOrEmpty(Line1) && string.IsNullOrEmpty(Line2);
}

/// <summary>
/// Footer configuration for a page (or the document's global default). See
/// docs/LEGACY_FEATURE_INVENTORY.md §3 for the full placement algorithm this feeds.
/// </summary>
public sealed record FooterConfig
{
    public bool Enabled { get; init; } = true;

    /// <summary>1-5 columns, equally spaced across the printable width.</summary>
    public IReadOnlyList<FooterColumn> Columns { get; init; } =
        Enumerable.Repeat(new FooterColumn("", ""), 5).ToArray();

    public string FontName { get; init; } = "Helvetica";
    public double FontSize { get; init; } = 13;
    public double LeftMargin { get; init; } = 36.0;
    public double RightMargin { get; init; } = 36.0;

    /// <summary>
    /// NOT a physical margin despite the legacy name it inherits conceptually — this is the
    /// desired gap between the page's actual content-bottom and the footer's visual top. The
    /// physical distance actually used when placing the footer is computed by
    /// FooterLayout.ComputeBottomMargin (Features layer), which also enforces a minimum physical
    /// safety margin from the page edge. See docs/LEGACY_FEATURE_INVENTORY.md §3.
    /// </summary>
    public double ContentGapPt { get; init; } = 72.0;

    /// <summary>Vertical gap, in points, between a column's line 1 and line 2.</summary>
    public double LineGapPt { get; init; } = 4.0;

    /// <summary>When the footer doesn't fit in the page's natural whitespace, shrink the page
    /// content to make room. When false, the footer is placed anyway even if it overlaps content.</summary>
    public bool CompressContent { get; init; } = true;
}
