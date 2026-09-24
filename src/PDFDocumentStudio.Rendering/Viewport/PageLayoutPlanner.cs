namespace PDFDocumentStudio.Rendering.Viewport;

public readonly record struct PageLayoutEntry(int PageIndex, double Top, double Height, double Width);

/// <summary>Continuous vertical page layout: stacks pages top-to-bottom with a fixed gap, at a
/// given zoom. Pure geometry — used to compute scrollbar extent and which pages are visible.</summary>
public sealed class PageLayoutPlanner
{
    public const double PageGap = 22.0;

    public IReadOnlyList<PageLayoutEntry> Layout(IReadOnlyList<(double Width, double Height)> pageSizesPt, double zoom)
    {
        var entries = new List<PageLayoutEntry>(pageSizesPt.Count);
        var y = 0.0;
        foreach (var (w, h) in pageSizesPt)
        {
            var width = w * zoom;
            var height = h * zoom;
            entries.Add(new PageLayoutEntry(entries.Count, y, height, width));
            y += height + PageGap;
        }
        return entries;
    }

    public static double TotalHeight(IReadOnlyList<PageLayoutEntry> layout) =>
        layout.Count == 0 ? 0 : layout[^1].Top + layout[^1].Height;

    /// <summary>Pages whose bounds intersect [visibleTop, visibleBottom] expanded by
    /// <paramref name="prefetchMargin"/> on each side — the legacy app's "~1 viewport rendered,
    /// evict past ~2 viewports" policy, generalized.</summary>
    public static IReadOnlyList<int> VisiblePageIndices(
        IReadOnlyList<PageLayoutEntry> layout, double visibleTop, double visibleBottom, double prefetchMargin)
    {
        var lo = visibleTop - prefetchMargin;
        var hi = visibleBottom + prefetchMargin;
        var result = new List<int>();
        foreach (var entry in layout)
        {
            if (entry.Top + entry.Height < lo) continue;
            if (entry.Top > hi) break;
            result.Add(entry.PageIndex);
        }
        return result;
    }
}
