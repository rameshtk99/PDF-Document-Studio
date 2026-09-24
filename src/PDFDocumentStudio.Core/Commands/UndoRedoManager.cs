namespace PDFDocumentStudio.Core.Commands;

/// <summary>
/// Linear undo/redo history over one <see cref="Model.EditorDocument"/>. Pushing a new command
/// after an undo discards the abandoned redo branch (matches the legacy app; no redo tree).
/// </summary>
public sealed class UndoRedoManager
{
    private const int MaxHistory = 100;

    private readonly Model.EditorDocument _document;
    private readonly List<IEditorCommand> _history = [];
    private int _index = -1; // index of the last-applied command; -1 = nothing applied yet

    public UndoRedoManager(Model.EditorDocument document) => _document = document;

    public bool CanUndo => _index >= 0;
    public bool CanRedo => _index < _history.Count - 1;

    public IReadOnlyList<IEditorCommand> History => _history;
    public int CurrentIndex => _index;

    public event Action? Changed;

    /// <summary>Executes <paramref name="command"/> and records it, discarding any redo branch.</summary>
    public void Push(IEditorCommand command)
    {
        command.Execute(_document);

        if (_index < _history.Count - 1)
            _history.RemoveRange(_index + 1, _history.Count - _index - 1);

        _history.Add(command);
        _index++;

        if (_history.Count > MaxHistory)
        {
            var overflow = _history.Count - MaxHistory;
            _history.RemoveRange(0, overflow);
            _index -= overflow;
        }

        Changed?.Invoke();
    }

    public IEditorCommand Undo()
    {
        if (!CanUndo) throw new InvalidOperationException("Nothing to undo.");
        var command = _history[_index];
        command.Undo(_document);
        _index--;
        Changed?.Invoke();
        return command;
    }

    public IEditorCommand Redo()
    {
        if (!CanRedo) throw new InvalidOperationException("Nothing to redo.");
        var command = _history[_index + 1];
        command.Execute(_document);
        _index++;
        Changed?.Invoke();
        return command;
    }

    public void Clear()
    {
        _history.Clear();
        _index = -1;
        Changed?.Invoke();
    }
}
