using PDFDocumentStudio.Core.Commands;
using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Features.Editing;

/// <summary>Facade over one open <see cref="EditorDocument"/>: undo/redo, selection, and the
/// common editing gestures, so the App layer never constructs Core commands directly.</summary>
public sealed class EditorSession
{
    private List<string> _selectedObjectIds = [];

    public EditorDocument Document { get; private set; }
    public UndoRedoManager UndoRedo { get; private set; }
    public IReadOnlyList<string> SelectedObjectIds => _selectedObjectIds;
    public int CurrentPage { get; set; } = 1;

    public event Action? Changed;

    public EditorSession(EditorDocument document)
    {
        Document = document;
        UndoRedo = new UndoRedoManager(document);
        UndoRedo.Changed += RaiseChanged;
    }

    public void Select(IEnumerable<string> objectIds)
    {
        _selectedObjectIds = objectIds.ToList();
        RaiseChanged();
    }

    public void ClearSelection() => Select([]);

    public string AddText(int pageNumber, double x, double y, double width, double height, TextStyle style)
    {
        var command = new AddObjectCommand(pageNumber, () => new TextPageObject { Style = style, X = x, Y = y, Width = width, Height = height });
        UndoRedo.Push(command);
        return command.LastAddedId!;
    }

    public string AddImage(int pageNumber, string imagePath, double x, double y, double width, double height)
    {
        var command = new AddObjectCommand(pageNumber, () => new ImagePageObject { ImagePath = imagePath, X = x, Y = y, Width = width, Height = height });
        UndoRedo.Push(command);
        return command.LastAddedId!;
    }

    public void DeleteSelected()
    {
        if (_selectedObjectIds.Count == 0) return;
        UndoRedo.Push(new DeleteObjectsCommand(_selectedObjectIds));
        ClearSelection();
    }

    public void ApplyStateChange(string description, IEnumerable<(string Id, ObjectSnapshot Before, ObjectSnapshot After)> entries)
    {
        var list = entries.ToList();
        if (list.Count == 0) return;
        UndoRedo.Push(new ChangeObjectStateCommand(description, list));
    }

    public IEditorCommand? Undo() => UndoRedo.CanUndo ? UndoRedo.Undo() : null;
    public IEditorCommand? Redo() => UndoRedo.CanRedo ? UndoRedo.Redo() : null;

    private void RaiseChanged() => Changed?.Invoke();
}
