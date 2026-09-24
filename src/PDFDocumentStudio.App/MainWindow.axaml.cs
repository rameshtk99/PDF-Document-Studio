using Avalonia;
using Avalonia.Animation;
using Avalonia.Animation.Easings;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using PDFDocumentStudio.App.Services;
using PDFDocumentStudio.App.ViewModels;
using PDFDocumentStudio.App.Views;
using PDFDocumentStudio.Pdf.Compression;

namespace PDFDocumentStudio.App;

public partial class MainWindow : Window
{
    private readonly MainViewModel _vm;

    public MainWindow()
    {
        InitializeComponent();
        _vm = new MainViewModel(new AppServices());
        DataContext = _vm;

        // Ctrl+wheel zoom must win over the ScrollViewer's own built-in wheel-scroll handling,
        // which otherwise consumes the event first (as a class handler) before a normal Bubble
        // handler on the same element ever runs. A Tunnel handler intercepts before that, so
        // Ctrl+wheel never also scrolls, and plain wheel (no Ctrl, not handled here) still scrolls
        // normally.
        DocumentScrollViewer.AddHandler(PointerWheelChangedEvent, OnCanvasPointerWheelChanged, RoutingStrategies.Tunnel);

        // Full-resolution page bitmaps are requested lazily for whatever's actually near the
        // viewport, not for the whole document at once (see MainViewModel.RequestVisiblePageBitmaps
        // for why). Two triggers, because neither alone is reliable: ScrollChanged fires on actual
        // scrolling (which a compositor-level offset scroll doesn't count as "layout"), while
        // LayoutUpdated fires whenever a layout pass actually completes — the initial container
        // realization after loading a document, and every resize from a zoom change. Relying on
        // ScrollChanged alone risks running once before containers have real measured bounds (top/
        // bottom both read as 0) and never firing again if the user hasn't scrolled yet.
        DocumentScrollViewer.ScrollChanged += (_, _) => RequestBitmapsForVisiblePages();
        DocumentItemsControl.LayoutUpdated += (_, _) => RequestBitmapsForVisiblePages();

        // Navigating to a page (thumbnail click, Prev/Next, selecting an object on another page,
        // applying a footer to a range, ...) must actually bring that page into view — otherwise
        // "current page" only changes a highlight, the canvas keeps showing wherever it already
        // was scrolled to, and that page's bitmap never gets requested because the viewport-based
        // loader only asks for pages that are actually scrolled into view.
        _vm.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName != nameof(MainViewModel.CurrentPage) || _vm.CurrentPage is not { } page) return;
            _vm.RequestVisiblePageBitmaps([page]);
            Dispatcher.UIThread.Post(() => ScrollToPage(page), DispatcherPriority.Loaded);
        };
    }

    /// <summary>Scrolls the document canvas so <paramref name="page"/> is in view (only if it
    /// isn't already, so selecting an object on an already-visible page doesn't jump the scroll
    /// position around), then requests bitmaps for whatever's now visible.</summary>
    private void ScrollToPage(PageViewModel page)
    {
        if (DocumentItemsControl.ContainerFromIndex(page.PageIndex) is not Control container) return;
        var top = container.TranslatePoint(new Point(0, 0), DocumentScrollViewer)?.Y;
        if (top is not { } topY) return;

        var viewportHeight = DocumentScrollViewer.Viewport.Height;
        if (topY < 0 || topY > Math.Max(0, viewportHeight - 60))
        {
            var maxY = Math.Max(0, DocumentScrollViewer.Extent.Height - viewportHeight);
            var newOffsetY = Math.Clamp(DocumentScrollViewer.Offset.Y + topY - 16, 0, maxY);
            DocumentScrollViewer.Offset = new Vector(DocumentScrollViewer.Offset.X, newOffsetY);
        }
        RequestBitmapsForVisiblePages();
    }

    /// <summary>Render window: pages whose bounds fall within one viewport-height above/below the
    /// visible area — matches the legacy app's documented "±1 viewport" windowed-rendering policy.</summary>
    private void RequestBitmapsForVisiblePages()
    {
        var itemsControl = DocumentItemsControl;
        var viewportHeight = DocumentScrollViewer.Viewport.Height;
        if (viewportHeight <= 0 || itemsControl.ItemCount == 0) return;

        var lo = -viewportHeight;
        var hi = viewportHeight * 2;
        var visible = new List<PageViewModel>();

        for (var i = 0; i < itemsControl.ItemCount; i++)
        {
            if (itemsControl.Items[i] is not PageViewModel page) continue;
            if (itemsControl.ContainerFromIndex(i) is not Control container) continue;
            var top = container.TranslatePoint(new Point(0, 0), DocumentScrollViewer)?.Y ?? double.NaN;
            if (double.IsNaN(top)) continue;
            var bottom = top + container.Bounds.Height;
            if (bottom >= lo && top <= hi) visible.Add(page);
        }

        if (visible.Count > 0) _vm.RequestVisiblePageBitmaps(visible);
    }

    private static readonly FilePickerFileType PdfFileType = new("PDF files") { Patterns = ["*.pdf"] };
    private static readonly FilePickerFileType ProjectFileType = new("PDF Document Studio project") { Patterns = ["*.pdfeditor"] };
    private static readonly FilePickerFileType ImageFileType = new("Images") { Patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.tiff"] };

    /// <summary>Shows the busy overlay for the duration of <paramref name="work"/>. Only used for
    /// operations that don't touch Avalonia-bound collections from a background thread — Export
    /// and Compress call straight into Core/Pdf-layer code with no UI-thread affinity concerns.</summary>
    private async Task RunBusyAsync(string message, Action work)
    {
        _vm.IsBusy = true;
        _vm.BusyMessage = message;
        try { await Task.Run(work); }
        finally { _vm.IsBusy = false; }
    }

    /// <summary>Sets the busy flag/message and lets one render pass actually paint the overlay
    /// before <paramref name="work"/> blocks the UI thread. Without this yield, setting IsBusy and
    /// then immediately calling synchronous load code never gives Avalonia a chance to draw the
    /// overlay first — it would appear only after work already finished, i.e. never.</summary>
    private async Task RunBusySynchronouslyAsync(string message, Action work)
    {
        _vm.IsBusy = true;
        _vm.BusyMessage = message;
        await Dispatcher.UIThread.InvokeAsync(() => { }, DispatcherPriority.Render);
        try { work(); }
        finally { _vm.IsBusy = false; }
    }

    private async void OnOpenPdf(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            FileTypeFilter = [PdfFileType],
        });
        if (files.Count == 0) return;
        try { await RunBusySynchronouslyAsync("Opening PDF...", () => _vm.LoadPdf(files[0].Path.LocalPath)); }
        catch (Exception ex) { _vm.StatusMessage = $"Could not open PDF: {ex.Message}"; }
    }

    /// <summary>Combines several PDFs into a brand-new document when nothing is open yet, or —
    /// matching the legacy app's "Import Multiple PDFs" reused on an already-open document —
    /// appends every page of the selected PDFs to the end of the current one instead of replacing
    /// it, so pages from 2-3 files can be arranged together via the normal page reorder.</summary>
    private async void OnImportPdfs(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            FileTypeFilter = [PdfFileType],
            AllowMultiple = true,
        });
        if (files.Count == 0) return;
        var paths = files.Select(f => f.Path.LocalPath).ToList();
        try
        {
            if (_vm.IsDocumentOpen)
                await RunBusySynchronouslyAsync("Adding PDFs...", () => _vm.InsertPdfPages(paths));
            else
                await RunBusySynchronouslyAsync("Opening PDFs...", () => _vm.LoadPdfs(paths));
        }
        catch (Exception ex) { _vm.StatusMessage = $"Could not import PDFs: {ex.Message}"; }
    }

    private async void OnOpenProject(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            FileTypeFilter = [ProjectFileType],
        });
        if (files.Count == 0) return;
        try { await RunBusySynchronouslyAsync("Opening project...", () => _vm.LoadProject(files[0].Path.LocalPath)); }
        catch (Exception ex) { _vm.StatusMessage = $"Could not open project: {ex.Message}"; }
    }

    private async void OnSaveProject(object? sender, RoutedEventArgs e)
    {
        var path = _vm.Services.Workspace.ProjectPath;
        if (path is null) { await SaveProjectAsAsync(); return; }
        try { _vm.SaveProjectAs(path); }
        catch (Exception ex) { _vm.StatusMessage = $"Could not save project: {ex.Message}"; }
    }

    private async void OnSaveProjectAs(object? sender, RoutedEventArgs e) => await SaveProjectAsAsync();

    private async Task SaveProjectAsAsync()
    {
        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            FileTypeChoices = [ProjectFileType],
            DefaultExtension = "pdfeditor",
            SuggestedFileName = "document.pdfeditor",
        });
        if (file is null) return;
        try { _vm.SaveProjectAs(file.Path.LocalPath); }
        catch (Exception ex) { _vm.StatusMessage = $"Could not save project: {ex.Message}"; }
    }

    private async void OnExportPdf(object? sender, RoutedEventArgs e)
    {
        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            FileTypeChoices = [PdfFileType],
            DefaultExtension = "pdf",
            SuggestedFileName = "export.pdf",
        });
        if (file is null) return;
        try { await RunBusyAsync("Exporting PDF...", () => _vm.ExportTo(file.Path.LocalPath)); }
        catch (Exception ex) { _vm.StatusMessage = $"Export failed: {ex.Message}"; }
    }

    private async void OnCompressPdf(object? sender, RoutedEventArgs e)
    {
        if (!_vm.IsDocumentOpen) { _vm.StatusMessage = "Open a PDF first."; return; }

        var dialog = new CompressDialogWindow();
        await dialog.ShowDialog(this);
        if (dialog.Result is not { } choice) return;

        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            FileTypeChoices = [PdfFileType],
            DefaultExtension = "pdf",
            SuggestedFileName = "compressed.pdf",
        });
        if (file is null) return;
        try { await RunBusyAsync("Compressing PDF...", () => _vm.CompressTo(file.Path.LocalPath, choice.MaxSizeMb, choice.Mode)); }
        catch (Exception ex) { _vm.StatusMessage = $"Compression failed: {ex.Message}"; }
    }

    private async void OnAddImage(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            FileTypeFilter = [ImageFileType],
        });
        if (files.Count == 0) return;
        _vm.AddImageToCurrentPage(files[0].Path.LocalPath);
    }

    private void OnAddText(object? sender, RoutedEventArgs e) => _vm.AddTextToCurrentPage();
    private void OnDelete(object? sender, RoutedEventArgs e) => _vm.DeleteSelected();
    private void OnUndo(object? sender, RoutedEventArgs e) => _vm.Undo();
    private void OnRedo(object? sender, RoutedEventArgs e) => _vm.Redo();
    private void OnZoomIn(object? sender, RoutedEventArgs e) => _vm.ZoomIn();
    private void OnZoomOut(object? sender, RoutedEventArgs e) => _vm.ZoomOut();
    private void OnZoomReset(object? sender, RoutedEventArgs e) => _vm.ZoomReset();

    private void OnZoomTextLostFocus(object? sender, RoutedEventArgs e) => _vm.CommitZoomPercentText(ZoomTextBox.Text ?? "");

    private void OnContextDuplicate(object? sender, RoutedEventArgs e) => _vm.DuplicateSelected();
    private void OnContextBringToFront(object? sender, RoutedEventArgs e) => _vm.BringSelectedToFront();
    private void OnContextSendToBack(object? sender, RoutedEventArgs e) => _vm.SendSelectedToBack();
    private void OnContextDeleteObject(object? sender, RoutedEventArgs e) => _vm.DeleteSelected();
    private void OnContextCopy(object? sender, RoutedEventArgs e) => _vm.CopySelected();
    private void OnContextPaste(object? sender, RoutedEventArgs e) => _vm.PasteObject();
    private void OnContextPasteInPlace(object? sender, RoutedEventArgs e) => _vm.PasteObjectInPlace();

    /// <summary>Ctrl+C/Ctrl+V select-an-object copy/paste — only when focus isn't in a text field,
    /// so it doesn't hijack normal text clipboard behavior in the footer panel.</summary>
    private void OnWindowKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.Key == Key.Delete && FocusManager?.GetFocusedElement() is not (TextBox or AutoCompleteBox or NumericUpDown))
        {
            _vm.DeleteSelected();
            e.Handled = true;
            return;
        }

        if (e.KeyModifiers != KeyModifiers.Control) return;
        if (FocusManager?.GetFocusedElement() is TextBox or AutoCompleteBox or NumericUpDown) return;

        if (e.Key == Key.C) { _vm.CopySelected(); e.Handled = true; }
        else if (e.Key == Key.V) { _vm.PasteObject(); e.Handled = true; }
        else if (e.Key == Key.Z) { _vm.Undo(); e.Handled = true; }
        else if (e.Key == Key.Y) { _vm.Redo(); e.Handled = true; }
    }

    /// <summary>Ctrl+wheel zooms, anchored on the pointer so the page under the cursor doesn't
    /// jump; plain wheel (no Ctrl) is left alone and scrolls normally — this handler only ever
    /// marks the event handled when Ctrl is held, so the two never mix.</summary>
    private void OnCanvasPointerWheelChanged(object? sender, PointerWheelEventArgs e)
    {
        if (!e.KeyModifiers.HasFlag(KeyModifiers.Control)) return;
        e.Handled = true;
        if (e.Delta.Y == 0) return;

        var scrollViewer = DocumentScrollViewer;
        var pointerPos = e.GetPosition(scrollViewer);
        var oldZoom = _vm.Zoom;
        var factor = e.Delta.Y > 0 ? 1.15 : 1 / 1.15;

        // Anchor the content point under the cursor: capture it in content-space before zooming,
        // then re-derive the scroll offset that keeps that same point under the cursor afterward.
        var contentPos = scrollViewer.Offset + new Vector(pointerPos.X, pointerPos.Y);
        _vm.ZoomBy(factor);
        var ratio = _vm.Zoom / oldZoom;
        if (Math.Abs(ratio - 1.0) < 0.0001) return;

        Dispatcher.UIThread.Post(() =>
        {
            var newContentPos = contentPos * ratio;
            var maxX = Math.Max(0, scrollViewer.Extent.Width - scrollViewer.Viewport.Width);
            var maxY = Math.Max(0, scrollViewer.Extent.Height - scrollViewer.Viewport.Height);
            scrollViewer.Offset = new Vector(
                Math.Clamp(newContentPos.X - pointerPos.X, 0, maxX),
                Math.Clamp(newContentPos.Y - pointerPos.Y, 0, maxY));
        }, DispatcherPriority.Render);
    }

    private void OnZoomTextKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.Key != Key.Enter) return;
        _vm.CommitZoomPercentText(ZoomTextBox.Text ?? "");
    }
    private void OnPrevPage(object? sender, RoutedEventArgs e) => _vm.GoToPage(_vm.CurrentPageNumber - 1);
    private void OnNextPage(object? sender, RoutedEventArgs e) => _vm.GoToPage(_vm.CurrentPageNumber + 1);
    private void OnApplyFooter(object? sender, RoutedEventArgs e) => _vm.ApplyFooter();
    private void OnSetFooterScopeAll(object? sender, RoutedEventArgs e) => _vm.FooterApplyScope = FooterApplyScope.All;
    private void OnSetFooterScopeSelected(object? sender, RoutedEventArgs e) => _vm.FooterApplyScope = FooterApplyScope.Selected;
    private void OnSetFooterScopeRange(object? sender, RoutedEventArgs e) => _vm.FooterApplyScope = FooterApplyScope.Range;
    private void OnLoadFooterDraft(object? sender, RoutedEventArgs e) => _vm.LoadSelectedFooterDraft();
    private void OnDeleteFooterDraft(object? sender, RoutedEventArgs e) => _vm.DeleteSelectedFooterDraft();
    private void OnAddFooterRow(object? sender, RoutedEventArgs e) => _vm.AddFooterRow();

    private void OnRemoveFooterRow(object? sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: FooterRowEdit row }) _vm.RemoveFooterRow(row);
    }

    private void OnSaveFooterDraft(object? sender, RoutedEventArgs e)
    {
        _vm.SaveCurrentAsFooterDraft(NewFooterDraftNameBox.Text ?? "");
        NewFooterDraftNameBox.Text = "";
    }
    private void OnExit(object? sender, RoutedEventArgs e) => Close();

    private void OnDeletePage(object? sender, RoutedEventArgs e) => _vm.DeletePage(_vm.CurrentPageNumber - 1);

    private void OnMovePageUp(object? sender, RoutedEventArgs e)
    {
        if (sender is not Control { DataContext: PageViewModel page }) return;
        if (page.PageIndex > 0) _vm.ReorderPage(page.PageIndex, page.PageIndex - 1);
    }

    private void OnMovePageDown(object? sender, RoutedEventArgs e)
    {
        if (sender is not Control { DataContext: PageViewModel page }) return;
        if (page.PageIndex < _vm.Pages.Count - 1) _vm.ReorderPage(page.PageIndex, page.PageIndex + 1);
    }

    private void OnMovePageToStart(object? sender, RoutedEventArgs e)
    {
        if (sender is not Control { DataContext: PageViewModel page }) return;
        if (page.PageIndex > 0) _vm.ReorderPage(page.PageIndex, 0);
    }

    private void OnMovePageToEnd(object? sender, RoutedEventArgs e)
    {
        if (sender is not Control { DataContext: PageViewModel page }) return;
        if (page.PageIndex < _vm.Pages.Count - 1) _vm.ReorderPage(page.PageIndex, _vm.Pages.Count - 1);
    }

    private void OnDeletePageContext(object? sender, RoutedEventArgs e)
    {
        if (sender is Control { DataContext: PageViewModel page }) _vm.DeletePage(page.PageIndex);
    }

    private static readonly DataFormat<string> PageDragFormat = DataFormat.CreateInProcessFormat<string>("pdfstudio-page-index");
    private static readonly DataFormat<string> FileGroupDragFormat = DataFormat.CreateInProcessFormat<string>("pdfstudio-file-path");

    private async void OnThumbnailPointerPressed(object? sender, PointerPressedEventArgs e)
    {
        if (sender is not Control { DataContext: PageViewModel page } control) return;
        if (!e.GetCurrentPoint(control).Properties.IsLeftButtonPressed) return;

        // Ctrl/Shift-click picks pages for the footer's "Selected pages" scope instead of
        // starting a drag or navigating.
        if (e.KeyModifiers.HasFlag(KeyModifiers.Shift)) { _vm.SelectPageRange(page); return; }
        if (e.KeyModifiers.HasFlag(KeyModifiers.Control)) { _vm.TogglePageSelection(page); return; }

        // A plain click should bring that page into the center canvas immediately; dragging still
        // uses the same pointer gesture, but selecting the page before the drag begins makes the
        // document follow the clicked thumbnail reliably without waiting for the drag/drop result.
        _vm.GoToPage(page.DisplayNumber);

        var transfer = new DataTransfer();
        transfer.Add(DataTransferItem.Create(PageDragFormat, page.PageIndex.ToString()));
        var effects = await DragDrop.DoDragDropAsync(e, transfer, DragDropEffects.Move);
        if (effects == DragDropEffects.None) _vm.GoToPage(page.DisplayNumber);
    }

    private void OnThumbnailDragOver(object? sender, DragEventArgs e)
    {
        e.DragEffects = e.DataTransfer.Formats.Contains(PageDragFormat) ? DragDropEffects.Move : DragDropEffects.None;
    }

    private async void OnThumbnailDrop(object? sender, DragEventArgs e)
    {
        if (sender is not Control { DataContext: PageViewModel targetPage }) return;
        var item = e.DataTransfer.Items.FirstOrDefault(i => i.Formats.Contains(PageDragFormat));
        if (item?.TryGetRaw(PageDragFormat) is not string raw || !int.TryParse(raw, out var sourceIndex)) return;

        // FLIP animation (First-Last-Invert-Play): capture where every thumbnail sits before the
        // reorder, let the WrapPanel re-lay-out instantly to the new order, then slide each moved
        // thumbnail from its old screen position back to its new one instead of an instant jump —
        // smooth, responsive drag feedback rather than an abrupt snap.
        var before = CaptureItemPositions(PagesItemsControl);
        _vm.ReorderPage(sourceIndex, targetPage.PageIndex);
        await Dispatcher.UIThread.InvokeAsync(() => { }, DispatcherPriority.Loaded);
        PlayFlip(PagesItemsControl, before);
    }

    private async void OnFileGroupPointerPressed(object? sender, PointerPressedEventArgs e)
    {
        if (sender is not Control { DataContext: FileGroupViewModel group } control) return;
        if (!e.GetCurrentPoint(control).Properties.IsLeftButtonPressed) return;

        var transfer = new DataTransfer();
        transfer.Add(DataTransferItem.Create(FileGroupDragFormat, group.SourcePath));
        await DragDrop.DoDragDropAsync(e, transfer, DragDropEffects.Move);
    }

    private void OnFileGroupDragOver(object? sender, DragEventArgs e)
    {
        e.DragEffects = e.DataTransfer.Formats.Contains(FileGroupDragFormat) ? DragDropEffects.Move : DragDropEffects.None;
    }

    private async void OnFileGroupDrop(object? sender, DragEventArgs e)
    {
        if (sender is not Control { DataContext: FileGroupViewModel targetGroup }) return;
        var item = e.DataTransfer.Items.FirstOrDefault(i => i.Formats.Contains(FileGroupDragFormat));
        if (item?.TryGetRaw(FileGroupDragFormat) is not string sourcePath) return;

        var before = CaptureItemPositions(FileGroupsItemsControl);
        _vm.ReorderFileGroup(sourcePath, targetGroup.SourcePath);
        await Dispatcher.UIThread.InvokeAsync(() => { }, DispatcherPriority.Loaded);
        PlayFlip(FileGroupsItemsControl, before);
    }

    private void OnRemoveFileGroup(object? sender, RoutedEventArgs e)
    {
        if (sender is Control { DataContext: FileGroupViewModel group }) _vm.RemoveFileGroup(group.SourcePath);
    }
    private void OnRemoveFileGroupContext(object? sender, RoutedEventArgs e)
    {
        if (sender is Control { DataContext: FileGroupViewModel group }) _vm.RemoveFileGroup(group.SourcePath);
    }

    private void OnToggleRightPanelCollapse(object? sender, RoutedEventArgs e)
    {
        _vm.IsRightPanelCollapsed = !_vm.IsRightPanelCollapsed;
    }

    private void OnSelectFooterTab(object? sender, RoutedEventArgs e) => _vm.SelectedRightTab = RightPanelTab.Footer;
    private void OnSelectFileOrganizerTab(object? sender, RoutedEventArgs e) => _vm.SelectedRightTab = RightPanelTab.FileOrganizer;
    private void OnSelectToolsTab(object? sender, RoutedEventArgs e) => _vm.SelectedRightTab = RightPanelTab.Tools;

    private static Dictionary<object, Point> CaptureItemPositions(ItemsControl itemsControl)
    {
        var positions = new Dictionary<object, Point>();
        for (var i = 0; i < itemsControl.ItemCount; i++)
        {
            var item = itemsControl.Items[i];
            if (item is not null && itemsControl.ContainerFromIndex(i) is Control container)
                positions[item] = container.TranslatePoint(new Point(0, 0), itemsControl) ?? default;
        }
        return positions;
    }

    private static void PlayFlip(ItemsControl itemsControl, Dictionary<object, Point> before)
    {
        for (var i = 0; i < itemsControl.ItemCount; i++)
        {
            var item = itemsControl.Items[i];
            if (item is null || !before.TryGetValue(item, out var oldPos)) continue;
            if (itemsControl.ContainerFromIndex(i) is not Control container) continue;

            var newPos = container.TranslatePoint(new Point(0, 0), itemsControl) ?? default;
            var delta = oldPos - newPos;
            if (delta.X == 0 && delta.Y == 0) continue;

            // Lift the moved thumbnail slightly so the motion feels more premium: a brief glow and
            // an over-sprung travel path is more natural than a plain linear slide.
            var transform = new TranslateTransform(delta.X, delta.Y);
            container.RenderTransform = transform;
            container.Opacity = 0.96;
            if (container is Border border)
            {
                border.BorderBrush = new SolidColorBrush(Color.FromArgb(120, 96, 165, 250));
                border.BorderThickness = new Thickness(1.5);
            }

            transform.Transitions =
            [
                new DoubleTransition { Property = TranslateTransform.XProperty, Duration = TimeSpan.FromMilliseconds(280), Easing = new CubicEaseOut() },
                new DoubleTransition { Property = TranslateTransform.YProperty, Duration = TimeSpan.FromMilliseconds(280), Easing = new CubicEaseOut() },
            ];
            transform.X = 0;
            transform.Y = 0;

            _ = Dispatcher.UIThread.InvokeAsync(async () =>
            {
                await Task.Delay(300);
                container.RenderTransform = null;
                container.Opacity = 1.0;
                if (container is Border b)
                {
                    b.BorderBrush = null;
                    b.BorderThickness = new Thickness(0);
                }
            });
        }
    }
}
