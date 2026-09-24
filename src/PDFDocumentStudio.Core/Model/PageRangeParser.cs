namespace PDFDocumentStudio.Core.Model;

/// <summary>Parses a typed page-range spec ("1-3, 7" or "all") into a sorted, deduped list of
/// 1-based page numbers — shared by the footer "page range" apply scope and (future) page-insert
/// pickers, matching the legacy app's single parser used by both features.</summary>
public static class PageRangeParser
{
    public static IReadOnlyList<int> Parse(string spec, int pageCount)
    {
        spec = spec.Trim();
        if (spec.Length == 0 || spec.Equals("all", StringComparison.OrdinalIgnoreCase))
            return Enumerable.Range(1, pageCount).ToList();

        var pages = new SortedSet<int>();
        foreach (var rawPart in spec.Split(','))
        {
            var part = rawPart.Trim();
            if (part.Length == 0) continue;

            var dash = part.IndexOf('-');
            if (dash > 0)
            {
                if (!int.TryParse(part[..dash].Trim(), out var start) || !int.TryParse(part[(dash + 1)..].Trim(), out var end))
                    throw new FormatException($"\"{part}\" is not a valid page or range.");
                if (start > end) (start, end) = (end, start);
                for (var p = start; p <= end; p++) pages.Add(p);
            }
            else
            {
                if (!int.TryParse(part, out var page))
                    throw new FormatException($"\"{part}\" is not a valid page or range.");
                pages.Add(page);
            }
        }

        var valid = pages.Where(p => p >= 1 && p <= pageCount).ToList();
        if (valid.Count == 0)
            throw new FormatException($"No valid pages in range (document has {pageCount} page(s)).");
        return valid;
    }
}
