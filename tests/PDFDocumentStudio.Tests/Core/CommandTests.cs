using PDFDocumentStudio.Core.Commands;
using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Tests.Core;

public class CommandTests
{
    private static EditorDocument MakeDocument()
    {
        var doc = new EditorDocument();
        doc.Pages.Add(new PageRef { SourcePath = "a.pdf", SourceIndex = 0, Width = 612, Height = 792 });
        return doc;
    }

    [Fact]
    public void AddObjectCommand_MintsNewIdOnEachRedo()
    {
        var doc = MakeDocument();
        var undoRedo = new UndoRedoManager(doc);
        var command = new AddObjectCommand(1, () => new TextPageObject { Style = new TextStyle { Text = "hi" } });

        undoRedo.Push(command);
        var firstId = command.LastAddedId;
        undoRedo.Undo();
        undoRedo.Redo();
        var secondId = command.LastAddedId;

        Assert.NotEqual(firstId, secondId);
        Assert.Single(doc.GetPageConfig(1).Objects);
    }

    [Fact]
    public void DeleteObjectsCommand_RestoresExactSnapshotOnUndo()
    {
        var doc = MakeDocument();
        var config = doc.GetOrCreatePageConfig(1);
        var obj = new TextPageObject { Id = "obj-1", Style = new TextStyle { Text = "keep me" }, Locked = true, ZIndex = 3 };
        config.Objects.Add(obj);

        var undoRedo = new UndoRedoManager(doc);
        undoRedo.Push(new DeleteObjectsCommand(["obj-1"]));
        Assert.Empty(doc.GetPageConfig(1).Objects);

        undoRedo.Undo();
        var restored = Assert.Single(doc.GetPageConfig(1).Objects);
        Assert.Equal("obj-1", restored.Id);
        Assert.True(restored.Locked);
        Assert.Equal(3, restored.ZIndex);
    }

    [Fact]
    public void ChangeObjectStateCommand_UndoRestoresFullBeforeSnapshot()
    {
        var doc = MakeDocument();
        var config = doc.GetOrCreatePageConfig(1);
        var obj = new ImagePageObject { Id = "img-1", ImagePath = "x.png", X = 10, Y = 10, Width = 50, Height = 50 };
        config.Objects.Add(obj);

        var before = ObjectSnapshot.Of(obj);
        obj.X = 100;
        obj.Y = 200;
        var after = ObjectSnapshot.Of(obj);

        var undoRedo = new UndoRedoManager(doc);
        undoRedo.Push(new ChangeObjectStateCommand("Move", [("img-1", before, after)]));
        Assert.Equal(100, obj.X);

        undoRedo.Undo();
        Assert.Equal(10, obj.X);
        Assert.Equal(10, obj.Y);

        undoRedo.Redo();
        Assert.Equal(100, obj.X);
    }

    [Fact]
    public void UndoRedoManager_PushingAfterUndo_DiscardsRedoBranch()
    {
        var doc = MakeDocument();
        var undoRedo = new UndoRedoManager(doc);
        undoRedo.Push(new AddObjectCommand(1, () => new TextPageObject()));
        undoRedo.Undo();
        undoRedo.Push(new AddObjectCommand(1, () => new TextPageObject()));

        Assert.False(undoRedo.CanRedo);
    }

    [Fact]
    public void PasteObjectsCommand_RemapsGroupIdsIndependentlyOfSource()
    {
        var doc = MakeDocument();
        var clipboard = new List<PageObject>
        {
            new TextPageObject { Style = new TextStyle { Text = "a" }, GroupId = "orig-group" },
            new TextPageObject { Style = new TextStyle { Text = "b" }, GroupId = "orig-group" },
        };

        var undoRedo = new UndoRedoManager(doc);
        var paste = new PasteObjectsCommand(1, clipboard);
        undoRedo.Push(paste);

        var pasted = doc.GetPageConfig(1).Objects;
        Assert.Equal(2, pasted.Count);
        Assert.Equal(pasted[0].GroupId, pasted[1].GroupId);
        Assert.NotEqual("orig-group", pasted[0].GroupId);
    }

    [Fact]
    public void ChangeGlobalFooterCommand_DoesNotDeleteObjectsOnAffectedPages()
    {
        var doc = MakeDocument();
        var config = doc.GetOrCreatePageConfig(1);
        config.Objects.Add(new TextPageObject { Style = new TextStyle { Text = "survives" } });

        var undoRedo = new UndoRedoManager(doc);
        undoRedo.Push(new ChangeGlobalFooterCommand(new FooterConfig { FontSize = 99 }));

        Assert.Single(doc.GetPageConfig(1).Objects);
        Assert.Equal(99, doc.GlobalSettings.FooterConfig.FontSize);
    }

    [Fact]
    public void DeletePageCommand_UndoRestoresPageAndItsObjects()
    {
        var doc = MakeDocument();
        doc.Pages.Add(new PageRef { SourcePath = "a.pdf", SourceIndex = 1, Width = 612, Height = 792 });
        doc.GetOrCreatePageConfig(2).Objects.Add(new TextPageObject { Style = new TextStyle { Text = "page 2 content" } });

        var undoRedo = new UndoRedoManager(doc);
        undoRedo.Push(new DeletePageCommand(0));
        Assert.Equal(1, doc.PageCount);

        undoRedo.Undo();
        Assert.Equal(2, doc.PageCount);
        Assert.Single(doc.GetPageConfig(2).Objects);
    }
}
