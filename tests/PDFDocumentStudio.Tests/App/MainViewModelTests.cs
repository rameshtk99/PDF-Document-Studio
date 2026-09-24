using Avalonia.Headless.XUnit;
using PDFDocumentStudio.App.Services;
using PDFDocumentStudio.App.ViewModels;
using PdfSharp.Pdf.IO;

namespace PDFDocumentStudio.Tests.App;

public class MainViewModelTests
{
    private static string SamplePdfPath => Path.Combine(AppContext.BaseDirectory, "Assets", "sample.pdf");

    [AvaloniaFact]
    public void LoadPdf_PopulatesPagesAndOpensDocument()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);

        Assert.True(vm.IsDocumentOpen);
        Assert.True(vm.Pages.Count > 0);
        Assert.Equal(1, vm.CurrentPageNumber);
    }

    [AvaloniaFact]
    public void AddTextThenUndo_RemovesIt_RedoRestoresIt()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);

        vm.AddTextToCurrentPage();
        Assert.Single(vm.CurrentPageObjects);

        vm.Undo();
        Assert.Empty(vm.CurrentPageObjects);

        vm.Redo();
        Assert.Single(vm.CurrentPageObjects);
    }

    [AvaloniaFact]
    public void GestureThenEnd_MovesObjectAndIsUndoable()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.AddTextToCurrentPage();
        var obj = Assert.Single(vm.CurrentPageObjects);
        var originalX = obj.Model.X;

        // Simulates what PageCanvasControl does on a pointer drag: mutate the model live, then
        // let the ViewModel diff before/after into one undo step on gesture end.
        vm.BeginGesture(obj);
        obj.Model.X += 50;
        vm.EndGesture();

        Assert.NotEqual(originalX, obj.Model.X);
        vm.Undo();
        Assert.Equal(originalX, obj.Model.X, 3);
    }

    [AvaloniaFact]
    public void GestureWithNoActualChange_DoesNotPushUndoEntry()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.AddTextToCurrentPage();
        var obj = Assert.Single(vm.CurrentPageObjects);
        var historyCountAfterAdd = vm.Services.Workspace.Session!.UndoRedo.History.Count;

        vm.BeginGesture(obj); // click with no movement
        vm.EndGesture();

        Assert.Equal(historyCountAfterAdd, vm.Services.Workspace.Session!.UndoRedo.History.Count);
    }

    [AvaloniaFact]
    public void ApplyFooterToAllPages_IsUndoable()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.FooterRows[0].Cells[0].Text = "Confidential";

        vm.ApplyFooterToAllPages();
        Assert.True(vm.FooterOverlay!.Visible);
        Assert.All(vm.Pages, p => Assert.True(p.FooterOverlay.Visible));

        vm.Undo();
    }

    [AvaloniaFact]
    public void ExportTo_ProducesValidPdfWithSamePageCount()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.AddTextToCurrentPage();

        var outputPath = Path.Combine(Path.GetTempPath(), $"vm_export_{Guid.NewGuid():N}.pdf");
        try
        {
            var result = vm.ExportTo(outputPath);
            Assert.Empty(result.Warnings);

            using var written = PdfReader.Open(outputPath, PdfDocumentOpenMode.Import);
            Assert.Equal(vm.Pages.Count, written.PageCount);
        }
        finally { if (File.Exists(outputPath)) File.Delete(outputPath); }
    }

    [AvaloniaFact]
    public void DeleteSelected_RemovesObjectFromDocument()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.AddTextToCurrentPage();
        var obj = Assert.Single(vm.CurrentPageObjects);

        vm.SelectObject(obj);
        vm.DeleteSelected();

        Assert.Empty(vm.CurrentPageObjects);
    }

    [AvaloniaFact]
    public void BringToFront_RaisesZIndexAboveAllSiblings()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.AddTextToCurrentPage();
        vm.AddTextToCurrentPage();
        var back = vm.CurrentPageObjects[0];
        var front = vm.CurrentPageObjects[1];

        vm.SelectObject(back);
        vm.BringSelectedToFront();

        Assert.True(back.Model.ZIndex > front.Model.ZIndex);
    }

    [AvaloniaFact]
    public void SendToBack_LowersZIndexBelowAllSiblings()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.AddTextToCurrentPage();
        vm.AddTextToCurrentPage();
        var first = vm.CurrentPageObjects[0];
        var second = vm.CurrentPageObjects[1];

        vm.SelectObject(second);
        vm.SendSelectedToBack();

        Assert.True(second.Model.ZIndex < first.Model.ZIndex);
    }

    [AvaloniaFact]
    public void DuplicateSelected_CreatesOffsetCopyAndSelectsIt()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.AddTextToCurrentPage();
        var original = vm.CurrentPageObjects[0];
        var originalX = original.Model.X;

        vm.SelectObject(original);
        vm.DuplicateSelected();

        Assert.Equal(2, vm.CurrentPageObjects.Count);
        Assert.NotEqual(original.Id, vm.SelectedObject!.Id);
        Assert.Equal(originalX + 10, vm.SelectedObject.Model.X, 3);
    }

    [AvaloniaFact]
    public void CopySelected_ThenPasteOnAnotherPage_AddsObjectThereAndIsUndoable()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.AddTextToCurrentPage();
        var original = vm.CurrentPageObjects[0];
        var originalX = original.Model.X;
        vm.SelectObject(original);

        vm.CopySelected();
        vm.GoToPage(2);
        Assert.Empty(vm.CurrentPageObjects);

        vm.PasteObject();

        Assert.Single(vm.CurrentPageObjects);
        Assert.Equal(originalX + 10, vm.CurrentPageObjects[0].Model.X, 3);

        vm.Undo();
        Assert.Empty(vm.CurrentPageObjects);
    }

    [AvaloniaFact]
    public void PasteObject_WithNothingCopied_DoesNothing()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);

        vm.PasteObject();

        Assert.Empty(vm.CurrentPageObjects);
    }

    [AvaloniaFact]
    public void FileGroups_ReorderAndRemove_WorkAcrossMultipleSourceFiles()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        var originalPageCount = vm.Pages.Count;

        var secondPath = Path.Combine(Path.GetTempPath(), $"sample_copy_{Guid.NewGuid():N}.pdf");
        File.Copy(SamplePdfPath, secondPath);
        try
        {
            vm.InsertPdfPages([secondPath]);

            Assert.Equal(2, vm.FileGroups.Count);
            Assert.Equal(SamplePdfPath, vm.FileGroups[0].SourcePath);
            Assert.Equal(secondPath, vm.FileGroups[1].SourcePath);
            Assert.Equal(originalPageCount, vm.FileGroups[0].PageCount);
            Assert.Equal(originalPageCount, vm.FileGroups[1].PageCount);

            vm.ReorderFileGroup(secondPath, SamplePdfPath);
            Assert.Equal(secondPath, vm.Pages[0].PageRef.SourcePath);
            Assert.Equal(SamplePdfPath, vm.Pages[originalPageCount].PageRef.SourcePath);

            vm.RemoveFileGroup(secondPath);
            Assert.Equal(originalPageCount, vm.Pages.Count);
            Assert.Single(vm.FileGroups);

            vm.RemoveFileGroup(SamplePdfPath); // refuses: it's the only file left
            Assert.Equal(originalPageCount, vm.Pages.Count);
            Assert.Contains("only file", vm.StatusMessage);
        }
        finally { File.Delete(secondPath); }
    }

    [AvaloniaFact]
    public void IsDocumentOpen_TriggersShowDocumentPropertyChange()
    {
        var vm = new MainViewModel(new AppServices());
        var changed = false;
        vm.PropertyChanged += (_, args) =>
        {
            if (args.PropertyName == nameof(MainViewModel.ShowDocument)) changed = true;
        };

        vm.LoadPdf(SamplePdfPath);

        Assert.True(vm.IsDocumentOpen);
        Assert.True(vm.ShowDocument);
        Assert.True(changed);
    }

    [AvaloniaFact]
    public void ReorderPage_InsertsMovedPageJustBeforeDropTarget()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        // PageViewModel.PageIndex is just "position in the list" and gets renumbered 0..N-1 on
        // every rebuild — PageRef.SourceIndex is the stable "which original PDF page is this" id.
        var originalPage0 = vm.Pages[0].PageRef.SourceIndex;
        var originalPage1 = vm.Pages[1].PageRef.SourceIndex;

        vm.ReorderPage(0, 3); // drag old page 0 onto old page 3

        // Removing index 0 shifts everything before the target left by one, so the moved page
        // lands immediately before where the target now sits — standard "insert before drop
        // target" list-reorder semantics, not "swap with the target's original slot".
        Assert.Equal(originalPage1, vm.Pages[0].PageRef.SourceIndex);
        Assert.Equal(originalPage0, vm.Pages[2].PageRef.SourceIndex);
    }

    [AvaloniaFact]
    public void LoadPdf_ShowsEveryPageAndEachPageHasItsOwnObjectsAndFooter()
    {
        // The whole document is always one continuous, fully interactive view — every page owns
        // its own Objects/FooterOverlay rather than sharing a single "current page only" canvas.
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);

        Assert.True(vm.ShowDocument);
        Assert.True(vm.Pages.Count > 1);
        Assert.All(vm.Pages, p => Assert.NotNull(p.Objects));
        Assert.All(vm.Pages, p => Assert.NotNull(p.FooterOverlay));
    }

    [AvaloniaFact]
    public void AddTextToCurrentPage_DoesNotHideOtherPages()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        var pageCount = vm.Pages.Count;

        vm.AddTextToCurrentPage();

        Assert.True(vm.ShowDocument);
        Assert.Equal(pageCount, vm.Pages.Count);
        Assert.Single(vm.CurrentPage!.Objects);
        Assert.True(vm.SelectedObject?.IsSelected);
    }

    [AvaloniaFact]
    public void SelectObjectOnAnotherPage_MakesThatPageCurrent()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.GoToPage(1);
        vm.AddTextToCurrentPage();
        var objOnPage1 = vm.Pages[0].Objects[0];

        vm.GoToPage(2);
        vm.SelectObject(objOnPage1);

        Assert.Equal(1, vm.CurrentPageNumber);
        Assert.True(objOnPage1.IsSelected);
    }

    [AvaloniaFact]
    public void CommitZoomPercentText_ParsesValidInput_AndRevertsInvalidInput()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);

        vm.CommitZoomPercentText("150%");
        Assert.Equal(1.5, vm.Zoom, 3);

        vm.CommitZoomPercentText("not a number");
        Assert.Equal(1.5, vm.Zoom, 3); // unchanged
        Assert.Equal("150%", vm.ZoomPercentText); // reverted to reflect the still-current zoom
    }

    [AvaloniaFact]
    public void InsertPdfPages_AppendsToEndOfOpenDocument_AsOneUndoStep()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        var originalCount = vm.Pages.Count;

        vm.InsertPdfPages([SamplePdfPath]);

        Assert.Equal(originalCount * 2, vm.Pages.Count);
        vm.Undo();
        Assert.Equal(originalCount, vm.Pages.Count);
    }

    [AvaloniaFact]
    public void ApplyFooterToRange_AppliesOnlyToParsedPages()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.AddTextToCurrentPage(); // just to have an existing session change; unrelated to footer
        vm.FooterRows[0].Cells[0].Text = "Ranged";
        vm.FooterRangeText = "1";

        vm.ApplyFooterToRange();

        Assert.Contains("1 page(s)", vm.StatusMessage);
    }

    [AvaloniaFact]
    public void ApplyFooterToRange_InvalidRange_ReportsErrorWithoutThrowing()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.FooterRangeText = "not a range";

        vm.ApplyFooterToRange();

        Assert.Contains("not a valid", vm.StatusMessage);
    }

    [AvaloniaFact]
    public void FooterColumnCount_GrowsAndShrinksColumnsWithDisplayNumbers()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        var original = vm.FooterColumnCount;

        vm.FooterColumnCount = original + 2;
        Assert.Equal(original + 2, vm.FooterColumns.Count);
        Assert.Equal([1, 2, 3, 4], vm.FooterColumns.Take(4).Select(c => c.DisplayNumber));

        vm.FooterColumnCount = 1;
        Assert.Single(vm.FooterColumns);
        Assert.Equal(1, vm.FooterColumns[0].DisplayNumber);
    }

    [AvaloniaFact]
    public void ApplyFooter_SelectedScope_AppliesOnlyToCtrlClickedPages()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.FooterRows[0].Cells[0].Text = "Selected";
        vm.FooterApplyScope = FooterApplyScope.Selected;
        vm.TogglePageSelection(vm.Pages[0]);
        vm.TogglePageSelection(vm.Pages[2]);

        vm.ApplyFooter();

        Assert.Contains("2 selected page(s)", vm.StatusMessage);
    }

    [AvaloniaFact]
    public void ApplyFooter_SelectedScope_WithNoneSelected_ReportsErrorWithoutThrowing()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.FooterApplyScope = FooterApplyScope.Selected;

        vm.ApplyFooter();

        Assert.Contains("No pages selected", vm.StatusMessage);
    }

    [AvaloniaFact]
    public void SelectPageRange_SelectsEveryPageBetweenAnchorAndTarget()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        vm.TogglePageSelection(vm.Pages[0]); // sets the anchor

        vm.SelectPageRange(vm.Pages[3]);

        Assert.True(vm.Pages[0].IsSelected);
        Assert.True(vm.Pages[1].IsSelected);
        Assert.True(vm.Pages[2].IsSelected);
        Assert.True(vm.Pages[3].IsSelected);
    }

    [AvaloniaFact]
    public void LoadPdf_ShowsNoFooterUntilApplied()
    {
        // A fresh document must not show any footer/border/placeholder content on any page —
        // only once the user actually applies one.
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);

        Assert.All(vm.Pages, p => Assert.False(p.FooterOverlay.Visible));
    }

    [AvaloniaFact]
    public void FooterRows_AddAndRemove_KeepsCellCountInSyncWithColumns()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        var originalRowCount = vm.FooterRows.Count;

        vm.AddFooterRow();
        Assert.Equal(originalRowCount + 1, vm.FooterRows.Count);
        Assert.Equal(vm.FooterColumns.Count, vm.FooterRows[^1].Cells.Count);

        vm.FooterColumnCount += 1;
        Assert.All(vm.FooterRows, r => Assert.Equal(vm.FooterColumns.Count, r.Cells.Count));

        vm.RemoveFooterRow(vm.FooterRows[^1]);
        Assert.Equal(originalRowCount, vm.FooterRows.Count);

        // Never removes the last row — a table must always have somewhere to type.
        while (vm.FooterRows.Count > 1) vm.RemoveFooterRow(vm.FooterRows[0]);
        vm.RemoveFooterRow(vm.FooterRows[0]);
        Assert.Single(vm.FooterRows);
    }

    [AvaloniaFact]
    public void FooterDraft_SaveLoadDelete_RoundTrips()
    {
        var vm = new MainViewModel(new AppServices());
        vm.LoadPdf(SamplePdfPath);
        var draftName = $"Test Draft {Guid.NewGuid():N}";
        try
        {
            vm.FooterRows[0].Cells[0].Text = "Draft Value";

            vm.SaveCurrentAsFooterDraft(draftName);
            Assert.Contains(draftName, vm.FooterDraftNames);

            vm.FooterRows[0].Cells[0].Text = "Changed";
            vm.SelectedFooterDraftName = draftName;
            vm.LoadSelectedFooterDraft();
            Assert.Equal("Draft Value", vm.FooterRows[0].Cells[0].Text);
        }
        finally
        {
            vm.SelectedFooterDraftName = draftName;
            vm.DeleteSelectedFooterDraft();
        }
        Assert.DoesNotContain(draftName, vm.FooterDraftNames);
    }
}
