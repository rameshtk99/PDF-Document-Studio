using PDFDocumentStudio.Core.Layout;
using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Tests.Core;

public class FooterLayoutCalculatorTests
{
    [Fact]
    public void Compute_EnoughWhitespace_PlacesContentRelativeWithoutCompression()
    {
        // Page 792pt tall, 30% blank below content (~237pt) — comfortably more than required.
        var footer = new FooterConfig { ContentGapPt = 20 };
        var placement = FooterLayoutCalculator.Compute(792, 0.30, footerTableHeightPt: 24, footer);

        Assert.False(placement.ContentCompressed);
        Assert.False(placement.OverlapsContent);
        Assert.True(placement.BottomMarginPt >= FooterLayoutCalculator.FooterPhysicalMarginPt);
    }

    [Fact]
    public void Compute_InsufficientWhitespace_CompressesAnchoredAtTop()
    {
        var footer = new FooterConfig { ContentGapPt = 72, CompressContent = true };
        var placement = FooterLayoutCalculator.Compute(792, 0.01, footerTableHeightPt: 30, footer); // ~8pt natural whitespace only

        Assert.True(placement.ContentCompressed);
        Assert.True(placement.ContentScaleY is > 0 and < 1);
        Assert.Equal(FooterLayoutCalculator.FooterPhysicalMarginPt, placement.BottomMarginPt);
    }

    [Fact]
    public void Compute_CompressionDisabled_OverlapsInsteadOfShrinking()
    {
        var footer = new FooterConfig { ContentGapPt = 72, CompressContent = false };
        var placement = FooterLayoutCalculator.Compute(792, 0.01, footerTableHeightPt: 30, footer);

        Assert.False(placement.ContentCompressed);
        Assert.True(placement.OverlapsContent);
    }

    [Fact]
    public void Compute_FooterTallerThanPage_GuardsAgainstNonPositiveScale()
    {
        var footer = new FooterConfig { ContentGapPt = 5000, CompressContent = true };
        var placement = FooterLayoutCalculator.Compute(100, 0.0, footerTableHeightPt: 30, footer);

        Assert.False(placement.ContentCompressed);
        Assert.True(placement.OverlapsContent);
    }
}

public class FooterTableLayoutTests
{
    private readonly FooterTableLayout _layout = new(new FakeFontMetricsProvider());

    private static FooterConfig MakeFooter(IReadOnlyList<FooterColumnDef> columns, IReadOnlyList<FooterRow> rows, bool showHeader = true) => new()
    {
        Table = new FooterTable { Columns = columns, Rows = rows, ShowHeader = showHeader },
    };

    [Fact]
    public void Layout_SubstitutesPageAndTotalTokensInCellsAndHeaders()
    {
        var footer = MakeFooter(
            [new FooterColumnDef { Header = "Page {page}" }],
            [new FooterRow { Cells = ["of {total}"] }]);

        var result = _layout.Layout(612, footer, pageNumber: 3, totalPages: 40);

        Assert.Equal("Page 3", result.Rows[0].Cells[0].Text.Lines[0].Text);
        Assert.Equal("of 40", result.Rows[1].Cells[0].Text.Lines[0].Text);
    }

    [Fact]
    public void Layout_TwoEqualColumns_SplitAvailableWidthEvenly()
    {
        var footer = MakeFooter(
            [new FooterColumnDef { Header = "Name" }, new FooterColumnDef { Header = "Role" }],
            [new FooterRow { Cells = ["Ramesh", "Manager"] }]);

        var result = _layout.Layout(612, footer, 1, 1); // avail = 612 - 36 - 36 = 540

        Assert.Equal(2, result.ColumnWidths.Count);
        Assert.Equal(result.ColumnWidths[0], result.ColumnWidths[1], 3);
        Assert.Equal(270, result.ColumnWidths[0], 3);
    }

    [Fact]
    public void Layout_ExplicitColumnWidth_LeavesRestForAutoColumns()
    {
        var footer = MakeFooter(
            [new FooterColumnDef { Header = "Fixed", WidthPt = 100 }, new FooterColumnDef { Header = "Auto1" }, new FooterColumnDef { Header = "Auto2" }],
            [new FooterRow { Cells = ["a", "b", "c"] }]);

        var result = _layout.Layout(612, footer, 1, 1); // avail=540, fixed=100, remaining=440/2=220 each

        Assert.Equal(100, result.ColumnWidths[0], 3);
        Assert.Equal(220, result.ColumnWidths[1], 3);
        Assert.Equal(220, result.ColumnWidths[2], 3);
    }

    [Fact]
    public void Layout_NoHeader_OmitsHeaderRow()
    {
        var footer = MakeFooter(
            [new FooterColumnDef()], [new FooterRow { Cells = ["x"] }], showHeader: false);

        var result = _layout.Layout(612, footer, 1, 1);

        Assert.Single(result.Rows);
        Assert.False(result.Rows[0].IsHeader);
    }

    [Fact]
    public void Layout_LongCellText_WrapsAndIncreasesRowHeight()
    {
        var shortFooter = MakeFooter([new FooterColumnDef()], [new FooterRow { Cells = ["short"] }], showHeader: false);
        var longFooter = MakeFooter([new FooterColumnDef()],
            [new FooterRow { Cells = ["a very long cell value that will definitely need to wrap across several lines"] }], showHeader: false);

        var shortResult = _layout.Layout(150, shortFooter, 1, 1);
        var longResult = _layout.Layout(150, longFooter, 1, 1);

        Assert.True(longResult.Rows[0].Cells[0].Text.Lines.Count > 1);
        Assert.True(longResult.TotalHeight > shortResult.TotalHeight);
    }
}
