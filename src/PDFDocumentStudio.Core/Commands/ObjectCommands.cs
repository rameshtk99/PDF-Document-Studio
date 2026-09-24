using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Core.Commands;

/// <summary>Adds one new page object. Mints a fresh id every time it (re)executes — including on
/// redo — matching the legacy contract that callers must never cache an object's id across an
/// undo/redo boundary; always re-resolve the live selection by re-reading the document.</summary>
public sealed class AddObjectCommand(int pageNumber, Func<PageObject> factory) : IEditorCommand
{
    private string? _lastAddedId;

    public string Description => "Add object";
    public bool AffectsPageStructure => false;
    public string? LastAddedId => _lastAddedId;

    public void Execute(EditorDocument document)
    {
        var obj = factory();
        obj.Id = Guid.NewGuid().ToString();
        obj.PageNumber = pageNumber;
        document.GetOrCreatePageConfig(pageNumber).Objects.Add(obj);
        _lastAddedId = obj.Id;
    }

    public void Undo(EditorDocument document)
    {
        document.GetOrCreatePageConfig(pageNumber).Objects.RemoveAll(o => o.Id == _lastAddedId);
    }
}

/// <summary>Deletes one or more objects (a single id covers the legacy DeleteObjectCommand case;
/// several covers DeleteManyCommand) as one undo step, restoring full snapshots including
/// lock/visible/group flags at their original list position on undo.</summary>
public sealed class DeleteObjectsCommand(IEnumerable<string> objectIds) : IEditorCommand
{
    private readonly List<string> _objectIds = objectIds.ToList();
    private readonly List<(int PageNumber, int Index, PageObject Snapshot)> _removed = [];

    public string Description => _objectIds.Count == 1 ? "Delete object" : "Delete objects";
    public bool AffectsPageStructure => false;

    public void Execute(EditorDocument document)
    {
        _removed.Clear();
        var targets = _objectIds
            .Select(document.FindObjectOwner)
            .Where(o => o is not null)
            .Select(o => o!.Value)
            .Select(o => (o.Config, o.Object, Index: o.Config.Objects.IndexOf(o.Object)))
            .OrderByDescending(t => t.Index); // remove highest index first so earlier indices stay valid

        foreach (var (config, obj, index) in targets)
        {
            _removed.Add((config.PageNumber, index, obj.Clone()));
            config.Objects.RemoveAt(index);
        }
    }

    public void Undo(EditorDocument document)
    {
        foreach (var (pageNumber, index, snapshot) in _removed.OrderBy(r => r.Index))
        {
            var config = document.GetOrCreatePageConfig(pageNumber);
            config.Objects.Insert(Math.Min(index, config.Objects.Count), snapshot.Clone());
        }
    }
}

/// <summary>
/// Applies a before/after <see cref="ObjectSnapshot"/> (the object's FULL geometry/paint/group
/// state, not just the fields that changed) to one or more objects as a single undo step.
/// Deliberately general: covers move, resize, rotate (single or multi-select), block z-order
/// changes (bring-to-front/send-to-back), and group/ungroup — every one of those is "some
/// objects' state changes together, as one gesture," which is exactly what a full snapshot diff
/// captures. Callers build entries by capturing <see cref="ObjectSnapshot.Of"/> before the
/// gesture starts and again once it ends (direct-manipulation UIs typically mutate the live
/// object during the drag for immediate visual feedback, then wrap the net change into this
/// command only once the gesture commits).
/// </summary>
public sealed class ChangeObjectStateCommand(
    string description,
    IEnumerable<(string Id, ObjectSnapshot Before, ObjectSnapshot After)> entries) : IEditorCommand
{
    private readonly List<(string Id, ObjectSnapshot Before, ObjectSnapshot After)> _entries = entries.ToList();

    public string Description => description;
    public bool AffectsPageStructure => false;

    public void Execute(EditorDocument document) => Apply(document, e => e.After);
    public void Undo(EditorDocument document) => Apply(document, e => e.Before);

    private void Apply(
        EditorDocument document,
        Func<(string Id, ObjectSnapshot Before, ObjectSnapshot After), ObjectSnapshot> pick)
    {
        foreach (var entry in _entries)
        {
            if (document.FindObjectOwner(entry.Id) is { } owner)
                pick(entry).ApplyTo(owner.Object);
        }
    }
}

/// <summary>
/// Generic single-property change (locked, visible, text style, image path, ...) for one or more
/// objects, applied via caller-supplied delegates rather than a fixed set of fields — covers
/// whatever the legacy app's ChangeObjectPropertyCommand handled without needing a new command
/// class per property.
/// </summary>
public sealed class ChangePropertyCommand(
    string description,
    IEnumerable<string> objectIds,
    Action<PageObject> applyBefore,
    Action<PageObject> applyAfter) : IEditorCommand
{
    private readonly List<string> _objectIds = objectIds.ToList();

    public string Description => description;
    public bool AffectsPageStructure => false;

    public void Execute(EditorDocument document) => Apply(document, applyAfter);
    public void Undo(EditorDocument document) => Apply(document, applyBefore);

    private void Apply(EditorDocument document, Action<PageObject> apply)
    {
        foreach (var id in _objectIds)
        {
            if (document.FindObjectOwner(id) is { } owner) apply(owner.Object);
        }
    }
}

/// <summary>
/// Pastes a clipboard snapshot of objects onto a target page as one undo step. Group ids are
/// remapped so pasted copies form their own independent group rather than joining the source
/// selection's group. Also backs the "Ctrl+Shift+drag duplicates and immediately drags the copy"
/// gesture: call <see cref="PatchFinalPositions"/> once the drag that follows the duplicate
/// commits, so the whole duplicate-and-reposition gesture undoes in one step instead of two.
/// </summary>
public sealed class PasteObjectsCommand(int targetPageNumber, IEnumerable<PageObject> clipboard) : IEditorCommand
{
    private readonly List<PageObject> _clipboard = clipboard.ToList();
    private List<string> _pastedIds = [];
    private IReadOnlyList<(double X, double Y)>? _finalPositions;

    public string Description => _clipboard.Count == 1 ? "Paste object" : "Paste objects";
    public bool AffectsPageStructure => false;
    public IReadOnlyList<string> PastedObjectIds => _pastedIds;

    public void Execute(EditorDocument document)
    {
        var groupIdMap = new Dictionary<string, string>();
        var config = document.GetOrCreatePageConfig(targetPageNumber);
        var pastedIds = new List<string>();

        for (var i = 0; i < _clipboard.Count; i++)
        {
            var clone = _clipboard[i].Clone();
            clone.Id = Guid.NewGuid().ToString();
            clone.PageNumber = targetPageNumber;

            if (clone.GroupId is { } oldGroup)
            {
                if (!groupIdMap.TryGetValue(oldGroup, out var newGroup))
                {
                    newGroup = Guid.NewGuid().ToString();
                    groupIdMap[oldGroup] = newGroup;
                }
                clone.GroupId = newGroup;
            }

            if (_finalPositions is not null)
            {
                clone.X = _finalPositions[i].X;
                clone.Y = _finalPositions[i].Y;
            }

            config.Objects.Add(clone);
            pastedIds.Add(clone.Id);
        }

        _pastedIds = pastedIds;
    }

    public void Undo(EditorDocument document)
    {
        document.GetOrCreatePageConfig(targetPageNumber).Objects.RemoveAll(o => _pastedIds.Contains(o.Id));
    }

    /// <summary>Records where each pasted object ended up after a follow-up drag, indexed to
    /// match the clipboard list passed to the constructor. Call before this command is pushed
    /// (or before it is next redone) so the fold-in applies from the very next Execute.</summary>
    public void PatchFinalPositions(IReadOnlyList<(double X, double Y)> finalPositions) =>
        _finalPositions = finalPositions;
}

/// <summary>
/// Commits one text-editing session (content + style + the auto-sized box's resulting geometry)
/// as a single undo step, pushed only once the user finishes editing (Esc / focus-out / tool
/// switch) — never per keystroke.
/// </summary>
public sealed class EditTextObjectCommand(
    string objectId,
    TextStyle beforeStyle, ObjectSnapshot beforeGeometry,
    TextStyle afterStyle, ObjectSnapshot afterGeometry) : IEditorCommand
{
    public string Description => "Edit text";
    public bool AffectsPageStructure => false;

    public void Execute(EditorDocument document) => Apply(document, afterStyle, afterGeometry);
    public void Undo(EditorDocument document) => Apply(document, beforeStyle, beforeGeometry);

    private void Apply(EditorDocument document, TextStyle style, ObjectSnapshot geometry)
    {
        if (document.FindObjectOwner(objectId)?.Object is TextPageObject text)
        {
            text.Style = style;
            geometry.ApplyTo(text);
        }
    }
}
