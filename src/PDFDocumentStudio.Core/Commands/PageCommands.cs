using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Core.Commands;

/// <summary>Deep snapshot of a document's page list + all per-page overlay configs, used by every
/// page-structure command to implement undo as "restore exactly how it was" rather than trying to
/// hand-compute an inverse for each operation (delete/move/insert/reorder all have different,
/// fiddly inverses — a snapshot sidesteps that entirely and is cheap: page counts are small).</summary>
internal sealed class DocumentPagesSnapshot
{
    private readonly List<PageRef> _pages;
    private readonly Dictionary<int, PageConfig> _pageConfigs;

    private DocumentPagesSnapshot(List<PageRef> pages, Dictionary<int, PageConfig> pageConfigs)
    {
        _pages = pages;
        _pageConfigs = pageConfigs;
    }

    public static DocumentPagesSnapshot Capture(EditorDocument document) => new(
        document.Pages.Select(p => p.Clone()).ToList(),
        document.PageConfigs.ToDictionary(kv => kv.Key, kv => kv.Value.Clone()));

    public void Restore(EditorDocument document)
    {
        document.Pages.Clear();
        document.Pages.AddRange(_pages.Select(p => p.Clone()));

        document.PageConfigs.Clear();
        foreach (var (pageNumber, config) in _pageConfigs)
            document.PageConfigs[pageNumber] = config.Clone();
    }
}

public sealed class DeletePageCommand(int index) : IEditorCommand
{
    private DocumentPagesSnapshot? _before;

    public string Description => "Delete page";
    public bool AffectsPageStructure => true;

    public void Execute(EditorDocument document)
    {
        _before ??= DocumentPagesSnapshot.Capture(document);
        document.DeletePage(index);
    }

    public void Undo(EditorDocument document) => _before!.Restore(document);
}

/// <summary>Self-inverse via full snapshot restore rather than a hand-computed reverse move —
/// simpler and just as correct as the legacy MovePage(to, from) inverse.</summary>
public sealed class MovePageCommand(int from, int to) : IEditorCommand
{
    private DocumentPagesSnapshot? _before;

    public string Description => "Move page";
    public bool AffectsPageStructure => true;

    public void Execute(EditorDocument document)
    {
        _before ??= DocumentPagesSnapshot.Capture(document);
        document.MovePage(from, to);
    }

    public void Undo(EditorDocument document) => _before!.Restore(document);
}

public sealed class InsertPagesCommand(int atIndex, IEnumerable<PageRef> refs) : IEditorCommand
{
    private readonly List<PageRef> _refs = refs.ToList();
    private DocumentPagesSnapshot? _before;

    public string Description => _refs.Count == 1 ? "Insert page" : "Insert pages";
    public bool AffectsPageStructure => true;

    public void Execute(EditorDocument document)
    {
        _before ??= DocumentPagesSnapshot.Capture(document);
        document.InsertPages(atIndex, _refs.Select(r => r.Clone()));
    }

    public void Undo(EditorDocument document) => _before!.Restore(document);
}

/// <summary>
/// Rebuilds the page list from a new ordering (any current index left out is an implicit delete).
/// Backs both whole-file reorder (File Organizer panel) and whole-file removal — moving or
/// removing every page of one source file, however non-contiguous, as one undo step — by having
/// the caller compute <paramref name="newOrderOldIndices"/> from <see cref="EditorDocument.FileGroups"/>.
/// </summary>
public sealed class SetPageOrderCommand(string description, IReadOnlyList<int> newOrderOldIndices) : IEditorCommand
{
    private DocumentPagesSnapshot? _before;

    public string Description => description;
    public bool AffectsPageStructure => true;

    public void Execute(EditorDocument document)
    {
        _before ??= DocumentPagesSnapshot.Capture(document);
        document.ReorderPages(newOrderOldIndices);
    }

    public void Undo(EditorDocument document) => _before!.Restore(document);
}
