namespace PDFDocumentStudio.Core.Model;

public enum FooterCellAlign { Left, Center, Right }

/// <summary>One column's header text, width, and cell alignment.</summary>
public sealed record FooterColumnDef
{
    public string Header { get; init; } = string.Empty;

    /// <summary>Explicit width in points, or null to share the remaining width equally with
    /// other auto-width columns.</summary>
    public double? WidthPt { get; init; }

    public FooterCellAlign Align { get; init; } = FooterCellAlign.Center;
}

/// <summary>One data row: cell text aligned by index to <see cref="FooterTable.Columns"/>.</summary>
public sealed record FooterRow
{
    public IReadOnlyList<string> Cells { get; init; } = [];
}

/// <summary>A footer rendered as a proper table: named columns, a header row, and data rows —
/// not free-form line pairs. E.g. columns "Name"/"Designation" with rows ("Ramesh","Manager"),
/// ("Suresh","Accountant").</summary>
public sealed record FooterTable
{
    public IReadOnlyList<FooterColumnDef> Columns { get; init; } = [];
    public IReadOnlyList<FooterRow> Rows { get; init; } = [];
    public bool ShowHeader { get; init; } = true;
    public bool ShowBorders { get; init; } = true;
}

/// <summary>
/// Footer configuration for a page (or the document's global default). See
/// docs/LEGACY_FEATURE_INVENTORY.md §3 for the placement algorithm this feeds.
/// </summary>
public sealed record FooterConfig
{
    // Disabled by default: a freshly opened document must show no footer at all on any page
    // until the user actually applies one — a page's config only gets Enabled=true (and real
    // content) via ChangeFooterCommand, which ApplyFooter always sets explicitly.
    public bool Enabled { get; init; } = false;

    public FooterTable Table { get; init; } = new()
    {
        Columns = [new FooterColumnDef { Header = "Name" }, new FooterColumnDef { Header = "Designation" }],
        Rows = [new FooterRow { Cells = ["", ""] }],
    };

    public string FontName { get; init; } = "Arial";
    public double FontSize { get; init; } = 11;
    public double LeftMargin { get; init; } = 36.0;
    public double RightMargin { get; init; } = 36.0;

    /// <summary>Gap between the page's actual content-bottom and the footer's visual top — not a
    /// physical margin. The physical distance actually used is computed by FooterLayoutCalculator,
    /// which also enforces a minimum physical safety margin from the page edge.</summary>
    public double ContentGapPt { get; init; } = 36.0;

    public double CellPaddingPt { get; init; } = 4.0;

    /// <summary>When the footer doesn't fit in the page's natural whitespace, shrink the page
    /// content to make room. When false, the footer is placed anyway even if it overlaps content.</summary>
    public bool CompressContent { get; init; } = true;
}
