namespace PDFDocumentStudio.Core.Model;

/// <summary>
/// The aggregate root of an editing session: an ordered list of pages (by stable identity, not by
/// source file) plus per-page overlay configuration. This is the in-memory equivalent of a
/// `.pdfeditor` project. Page order/identity changes MUST go through the methods on this class —
/// they are the only place that keeps page_configs' 1-based keys and every contained PageObject's
/// PageNumber in sync with the page list. See docs/LEGACY_FEATURE_INVENTORY.md §1.
/// </summary>
public sealed class EditorDocument
{
    /// <summary>The file path this document/project most recently identified as (first-loaded source,
    /// or the .pdfeditor path once saved). Kept for compatibility/display purposes only.</summary>
    public string? PrimaryPath { get; set; }

    public List<PageRef> Pages { get; } = [];

    public GlobalSettings GlobalSettings { get; set; } = new();

    /// <summary>Keyed by 1-based display page number. A page with no entry uses a config freshly
    /// synthesized from <see cref="GlobalSettings"/> (see <see cref="GetPageConfig"/>).</summary>
    public Dictionary<int, PageConfig> PageConfigs { get; } = [];

    public DateTimeOffset Created { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset Modified { get; set; } = DateTimeOffset.UtcNow;

    public int PageCount => Pages.Count;

    /// <summary>Returns this page's own config if set, otherwise a fresh (unsaved) copy synthesized
    /// from the document's global defaults. Mutating the returned instance has no effect until
    /// passed to <see cref="SetPageConfig"/> — matches the legacy get_page_config contract.</summary>
    public PageConfig GetPageConfig(int pageNumber)
    {
        if (PageConfigs.TryGetValue(pageNumber, out var existing))
            return existing;

        return new PageConfig
        {
            PageNumber = pageNumber,
            FooterConfig = GlobalSettings.FooterConfig,
            AutoLayout = GlobalSettings.AutoLayout,
            PreserveOriginal = GlobalSettings.PreserveOriginal,
            OverridesGlobal = false,
        };
    }

    public void SetPageConfig(int pageNumber, PageConfig config)
    {
        config.PageNumber = pageNumber;
        PageConfigs[pageNumber] = config;
    }

    /// <summary>Like <see cref="GetPageConfig"/>, but materializes (stores) the config if this page
    /// didn't have its own yet — needed before mutating a page's objects/footer in place.</summary>
    public PageConfig GetOrCreatePageConfig(int pageNumber)
    {
        if (!PageConfigs.TryGetValue(pageNumber, out var config))
        {
            config = GetPageConfig(pageNumber);
            PageConfigs[pageNumber] = config;
        }
        return config;
    }

    /// <summary>Searches every page's stored config for an object by id.</summary>
    public (PageConfig Config, PageObject Object)? FindObjectOwner(string objectId)
    {
        foreach (var config in PageConfigs.Values)
        {
            var obj = config.Objects.FirstOrDefault(o => o.Id == objectId);
            if (obj is not null) return (config, obj);
        }
        return null;
    }

    /// <summary>Removes the page at <paramref name="index"/> (0-based) and its overlay config,
    /// shifting every later page's config/objects down by one position. One undo step.</summary>
    public void DeletePage(int index)
    {
        if (index < 0 || index >= Pages.Count) throw new ArgumentOutOfRangeException(nameof(index));
        var deletedPosition = index + 1;
        Pages.RemoveAt(index);

        var remap = new Dictionary<int, int?>();
        foreach (var pos in PageConfigs.Keys.ToArray())
        {
            remap[pos] = pos == deletedPosition ? null : pos > deletedPosition ? pos - 1 : pos;
        }
        ApplyRemap(remap);
    }

    /// <summary>Moves the page at 0-based <paramref name="from"/> to 0-based <paramref name="to"/>,
    /// shifting every page config in between by one position. Self-inverse: MovePage(to, from) undoes it.</summary>
    public void MovePage(int from, int to)
    {
        if (from < 0 || from >= Pages.Count) throw new ArgumentOutOfRangeException(nameof(from));
        if (to < 0 || to >= Pages.Count) throw new ArgumentOutOfRangeException(nameof(to));
        if (from == to) return;

        var page = Pages[from];
        Pages.RemoveAt(from);
        Pages.Insert(to, page);

        var fromPos = from + 1;
        var toPos = to + 1;
        var remap = new Dictionary<int, int?>();
        foreach (var pos in PageConfigs.Keys.ToArray())
        {
            if (pos == fromPos) { remap[pos] = toPos; continue; }
            if (fromPos < toPos && pos > fromPos && pos <= toPos) { remap[pos] = pos - 1; continue; }
            if (fromPos > toPos && pos >= toPos && pos < fromPos) { remap[pos] = pos + 1; continue; }
            remap[pos] = pos;
        }
        ApplyRemap(remap);
    }

    /// <summary>Inserts pages at 0-based <paramref name="atIndex"/>, shifting later page configs
    /// forward by the number of inserted pages. The new pages start with no overlay config
    /// (fresh defaults via <see cref="GetPageConfig"/>).</summary>
    public void InsertPages(int atIndex, IEnumerable<PageRef> refs)
    {
        var list = refs as IReadOnlyList<PageRef> ?? refs.ToList();
        if (list.Count == 0) return;
        if (atIndex < 0 || atIndex > Pages.Count) throw new ArgumentOutOfRangeException(nameof(atIndex));

        Pages.InsertRange(atIndex, list);

        var insertedAtPosition = atIndex + 1;
        var remap = new Dictionary<int, int?>();
        foreach (var pos in PageConfigs.Keys.ToArray())
        {
            remap[pos] = pos >= insertedAtPosition ? pos + list.Count : pos;
        }
        ApplyRemap(remap);
    }

    /// <summary>
    /// Rebuilds the page list from <paramref name="newOrderOldIndices"/> — a permutation/subset of
    /// current 0-based indices. Any current index not present is implicitly deleted (matches the
    /// legacy reorder_pages contract).
    /// </summary>
    public void ReorderPages(IReadOnlyList<int> newOrderOldIndices)
    {
        var newPages = newOrderOldIndices.Select(i => Pages[i]).ToList();

        var remap = new Dictionary<int, int?>();
        for (var newIdx = 0; newIdx < newOrderOldIndices.Count; newIdx++)
        {
            var oldPos = newOrderOldIndices[newIdx] + 1;
            remap[oldPos] = newIdx + 1;
        }
        foreach (var pos in PageConfigs.Keys.ToArray())
        {
            if (!remap.ContainsKey(pos)) remap[pos] = null;
        }

        Pages.Clear();
        Pages.AddRange(newPages);
        ApplyRemap(remap);
    }

    private void ApplyRemap(IReadOnlyDictionary<int, int?> oldPositionToNewPosition)
    {
        var updated = new Dictionary<int, PageConfig>();
        foreach (var (oldPos, config) in PageConfigs)
        {
            if (!oldPositionToNewPosition.TryGetValue(oldPos, out var newPos) || newPos is null)
                continue; // page (and its overlay config) was deleted

            config.PageNumber = newPos.Value;
            foreach (var obj in config.Objects) obj.PageNumber = newPos.Value;
            updated[newPos.Value] = config;
        }

        PageConfigs.Clear();
        foreach (var (pos, config) in updated) PageConfigs[pos] = config;
    }

    /// <summary>Pages grouped by source file, in order of first appearance — backs a "file organizer"
    /// view; a file's pages may be non-contiguous after per-page reordering and still form one group.</summary>
    public IReadOnlyList<(string SourcePath, IReadOnlyList<int> PageIndices)> FileGroups()
    {
        var order = new List<string>();
        var groups = new Dictionary<string, List<int>>();
        for (var i = 0; i < Pages.Count; i++)
        {
            var path = Pages[i].SourcePath;
            if (!groups.TryGetValue(path, out var list))
            {
                list = [];
                groups[path] = list;
                order.Add(path);
            }
            list.Add(i);
        }
        return order.Select(p => (p, (IReadOnlyList<int>)groups[p])).ToList();
    }
}
