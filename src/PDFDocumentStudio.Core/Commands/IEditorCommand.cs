namespace PDFDocumentStudio.Core.Commands;

/// <summary>
/// One undoable unit of work against an <see cref="Model.EditorDocument"/>. Commands are
/// constructed with all the state they need (before/after snapshots) and are immediately applied
/// via <see cref="Execute"/> when pushed onto an <see cref="UndoRedoManager"/> — "redo" simply
/// re-invokes <see cref="Execute"/>.
/// <para/>
/// Invariant carried over from the legacy app: ONE USER GESTURE = ONE COMMAND. A whole drag, a
/// whole typing session, a whole multi-object operation is one command — never one command per
/// intermediate step. See docs/LEGACY_FEATURE_INVENTORY.md §9.
/// </summary>
public interface IEditorCommand
{
    /// <summary>Short, user-facing label (status bar / history list), e.g. "Move object".</summary>
    string Description { get; }

    /// <summary>
    /// True for commands that change page count/order (delete/move/insert page, file reorder).
    /// The UI can use this to decide whether an undo/redo needs a full page-layout/thumbnail
    /// rebuild versus a cheap overlay-only redraw.
    /// </summary>
    bool AffectsPageStructure { get; }

    void Execute(Model.EditorDocument document);
    void Undo(Model.EditorDocument document);
}
