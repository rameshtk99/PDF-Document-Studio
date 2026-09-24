using System.Collections.ObjectModel;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using PDFDocumentStudio.App.Services;
using PDFDocumentStudio.Core.Commands;
using PDFDocumentStudio.Core.Model;
using PDFDocumentStudio.Features.Editing;
using PDFDocumentStudio.Features.Footer;
using PDFDocumentStudio.Pdf.Compression;
using PDFDocumentStudio.Pdf.Export;
using PDFDocumentStudio.Pdf.Rendering;
using PDFDocumentStudio.Rendering.Caching;

namespace PDFDocumentStudio.App.ViewModels;

public enum RightPanelTab { Footer, FileOrganizer, Tools }

/// <summary>
/// The whole document is always shown as one continuous, fully interactive view — every page
/// renders its own footer and its own objects (see <see cref="PageViewModel"/>), and any page can
/// be edited without hiding the rest of the document. There used to be a second "single page"
/// mode whose canvas was the only place footers/objects were drawn at all; that's what made a
/// footer or a freshly-added text box appear on only one page. Don't reintroduce a mode where any
/// page's footer/objects are only rendered for the "current" page — every page must stay
/// self-sufficient.
/// </summary>
public sealed partial class MainViewModel : ObservableObject
{
    private readonly AppServices _services;
    private ObjectViewModel? _dragObject;
    private ObjectSnapshot? _dragStart;

    public AppServices Services => _services;
    public ObservableCollection<PageViewModel> Pages { get; } = [];
    public ObservableCollection<FileGroupViewModel> FileGroups { get; } = [];
    public ObservableCollection<FooterColumnEdit> FooterColumns { get; } = [];
    public ObservableCollection<FooterRowEdit> FooterRows { get; } = [];
    public ObservableCollection<string> FooterDraftNames { get; } = [];

    /// <summary>Convenience read-only view of whichever page is current — most toolbar-level
    /// operations (z-order, duplicate, copy) act on it. Individual pages own the real collection.</summary>
    public IReadOnlyList<ObjectViewModel> CurrentPageObjects => CurrentPage is { } page ? page.Objects : [];
    public FooterOverlayViewModel? FooterOverlay => CurrentPage?.FooterOverlay;

    [ObservableProperty] private RightPanelTab _selectedRightTab = RightPanelTab.Footer;
    [ObservableProperty] private bool _isRightPanelCollapsed;
    public bool ShowFooterTab => SelectedRightTab == RightPanelTab.Footer;
    public bool ShowFileOrganizerTab => SelectedRightTab == RightPanelTab.FileOrganizer;
    public bool ShowToolsTab => SelectedRightTab == RightPanelTab.Tools;
    public double RightPanelWidth => IsRightPanelCollapsed ? 52 : 320;
    public string RightPanelToggleGlyph => IsRightPanelCollapsed ? "»" : "«";

    partial void OnSelectedRightTabChanged(RightPanelTab value)
    {
        OnPropertyChanged(nameof(ShowFooterTab));
        OnPropertyChanged(nameof(ShowFileOrganizerTab));
        OnPropertyChanged(nameof(ShowToolsTab));
    }

    partial void OnIsRightPanelCollapsedChanged(bool value)
    {
        OnPropertyChanged(nameof(RightPanelWidth));
        OnPropertyChanged(nameof(RightPanelToggleGlyph));
    }

    [ObservableProperty] private double _zoom = 1.0;
    [ObservableProperty] private int _currentPageNumber = 1;
    [ObservableProperty] private string _statusMessage = "Ready";
    [ObservableProperty] private bool _isDocumentOpen;
    partial void OnIsDocumentOpenChanged(bool value) => OnPropertyChanged(nameof(ShowDocument));
    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private string _busyMessage = "Working...";
    [ObservableProperty] private ObjectViewModel? _selectedObject;
    [ObservableProperty] private string _footerFontName = "Arial";
    [ObservableProperty] private double _footerFontSize = 11;
    [ObservableProperty] private double _footerGapPt = 36;
    [ObservableProperty] private bool _footerCompressContent = true;
    [ObservableProperty] private bool _footerShowHeader = true;
    [ObservableProperty] private bool _footerShowBorders = true;
    [ObservableProperty] private string? _selectedFooterDraftName;
    [ObservableProperty] private PageViewModel? _currentPage;

    public IReadOnlyList<string> AvailableFontNames { get; private set; } = [];

    public double ScreenScale => Zoom * (150.0 / 72.0);
    public double RenderDpi => Zoom * 150.0;
    private EditorSession? Session => _services.Workspace.Session;

    public MainViewModel(AppServices services)
    {
        _services = services;
        AvailableFontNames = _services.FontRegistry.FontsByDisplayName.Keys.OrderBy(n => n, StringComparer.OrdinalIgnoreCase).ToList();
        LoadFooterEditorFromConfig(new FooterConfig());
        RefreshFooterDraftNames();
        _services.BitmapCache.Ready += OnBitmapReady;
        _services.BitmapCache.RenderFailed += OnBitmapRenderFailed;
    }

    private bool _reportedRenderFailure;

    /// <summary>Surfaces the first page-render failure instead of leaving the page silently blank
    /// with no visible cause — only the first, since a systemic failure (e.g. a corrupt PDF or a
    /// missing native renderer dependency) would otherwise spam one message per page.</summary>
    private void OnBitmapRenderFailed(string sourcePath, Exception ex)
    {
        if (_reportedRenderFailure) return;
        _reportedRenderFailure = true;
        Dispatcher.UIThread.Post(() =>
            StatusMessage = $"Could not render '{Path.GetFileName(sourcePath)}': {ex.Message}");
    }

    private void RefreshFooterDraftNames()
    {
        FooterDraftNames.Clear();
        foreach (var draft in _services.FooterDrafts.Load()) FooterDraftNames.Add(draft.Name);
    }

    public void SaveCurrentAsFooterDraft(string name)
    {
        if (string.IsNullOrWhiteSpace(name)) return;
        _services.FooterDrafts.SaveOrUpdate(name.Trim(), BuildFooterConfigFromEditor());
        RefreshFooterDraftNames();
        SelectedFooterDraftName = name.Trim();
        StatusMessage = $"Saved footer preset \"{name.Trim()}\".";
    }

    public void LoadSelectedFooterDraft()
    {
        if (SelectedFooterDraftName is not { } name) return;
        var draft = _services.FooterDrafts.Load().FirstOrDefault(d => d.Name == name);
        if (draft is null) return;
        LoadFooterEditorFromConfig(draft.Config);
        UpdateCurrentPageFooterDraftPreview();
        StatusMessage = $"Loaded footer preset \"{name}\".";
    }

    public void DeleteSelectedFooterDraft()
    {
        if (SelectedFooterDraftName is not { } name) return;
        _services.FooterDrafts.Delete(name);
        RefreshFooterDraftNames();
        SelectedFooterDraftName = null;
        StatusMessage = $"Deleted footer preset \"{name}\".";
    }

    /// <summary>Number of footer columns — growing appends a blank column (and a blank cell to
    /// every existing row); shrinking drops the last column (and its cell from every row).</summary>
    public int FooterColumnCount
    {
        get => FooterColumns.Count;
        set
        {
            value = Math.Max(1, value);
            while (FooterColumns.Count < value)
            {
                var column = new FooterColumnEdit { DisplayNumber = FooterColumns.Count + 1 };
                HookFooterColumn(column);
                FooterColumns.Add(column);
                foreach (var row in FooterRows) HookCell(AddCell(row));
            }
            while (FooterColumns.Count > value)
            {
                FooterColumns.RemoveAt(FooterColumns.Count - 1);
                foreach (var row in FooterRows)
                    if (row.Cells.Count > 0) row.Cells.RemoveAt(row.Cells.Count - 1);
            }
            RenumberFooterColumns();
            OnPropertyChanged();
            UpdateCurrentPageFooterDraftPreview();
        }
    }

    private void RenumberFooterColumns()
    {
        for (var i = 0; i < FooterColumns.Count; i++) FooterColumns[i].DisplayNumber = i + 1;
    }

    private void HookFooterColumn(FooterColumnEdit column) => column.PropertyChanged += (_, _) => UpdateCurrentPageFooterDraftPreview();
    private void HookCell(FooterCellEdit cell) => cell.PropertyChanged += (_, _) => UpdateCurrentPageFooterDraftPreview();

    private static FooterCellEdit AddCell(FooterRowEdit row)
    {
        var cell = new FooterCellEdit();
        row.Cells.Add(cell);
        return cell;
    }

    /// <summary>Appends one blank data row, sized to the current column count — matches "Add Row"
    /// in the footer table editor.</summary>
    public void AddFooterRow()
    {
        var row = new FooterRowEdit();
        for (var i = 0; i < FooterColumns.Count; i++) HookCell(AddCell(row));
        FooterRows.Add(row);
        UpdateCurrentPageFooterDraftPreview();
    }

    /// <summary>Removes one data row — always leaves at least one row so the table never becomes
    /// header-only with nothing to type into.</summary>
    public void RemoveFooterRow(FooterRowEdit row)
    {
        if (FooterRows.Count <= 1) return;
        FooterRows.Remove(row);
        UpdateCurrentPageFooterDraftPreview();
    }

    private void LoadFooterEditorFromConfig(FooterConfig config)
    {
        FooterColumns.Clear();
        FooterRows.Clear();

        var columnCount = Math.Max(1, config.Table.Columns.Count);
        for (var i = 0; i < columnCount; i++)
        {
            var def = i < config.Table.Columns.Count ? config.Table.Columns[i] : new FooterColumnDef();
            var vm = new FooterColumnEdit { DisplayNumber = i + 1, Header = def.Header, WidthPt = def.WidthPt, Align = def.Align };
            HookFooterColumn(vm);
            FooterColumns.Add(vm);
        }

        var rowCount = Math.Max(1, config.Table.Rows.Count);
        for (var r = 0; r < rowCount; r++)
        {
            var row = new FooterRowEdit();
            var sourceRow = r < config.Table.Rows.Count ? config.Table.Rows[r] : null;
            for (var c = 0; c < columnCount; c++)
            {
                var cell = AddCell(row);
                cell.Text = sourceRow is not null && c < sourceRow.Cells.Count ? sourceRow.Cells[c] : string.Empty;
                HookCell(cell);
            }
            FooterRows.Add(row);
        }

        OnPropertyChanged(nameof(FooterColumnCount));

        // Fall back to a font this machine actually has installed rather than trusting a
        // default/saved name (e.g. "Arial") blindly — matters most on Linux/macOS.
        FooterFontName = _services.FontRegistry.FontsByDisplayName.ContainsKey(config.FontName)
            ? config.FontName
            : _services.FontRegistry.FallbackFontName ?? config.FontName;
        FooterFontSize = config.FontSize;
        FooterGapPt = config.ContentGapPt;
        FooterCompressContent = config.CompressContent;
        FooterShowHeader = config.Table.ShowHeader;
        FooterShowBorders = config.Table.ShowBorders;
    }

    public void LoadPdf(string path)
    {
        _services.Workspace.OpenPdf(path);
        AfterDocumentLoaded();
    }

    public void LoadPdfs(IReadOnlyList<string> paths)
    {
        _services.Workspace.OpenPdfs(paths);
        AfterDocumentLoaded();
    }

    /// <summary>Appends every page of each selected PDF to the end of the already-open document —
    /// one undo step — so 2-3 files can be combined and then arranged via the normal page reorder,
    /// matching the legacy app's "Import Multiple PDFs" reused on an open document.</summary>
    public void InsertPdfPages(IReadOnlyList<string> paths)
    {
        if (Session is null || paths.Count == 0) return;
        var refs = new List<PageRef>();
        foreach (var path in paths) refs.AddRange(_services.PdfLoader.BuildPageRefs(path));
        if (refs.Count == 0) return;

        Session.UndoRedo.Push(new InsertPagesCommand(Session.Document.Pages.Count, refs));
        RebuildPagesAfterStructureChange();
        StatusMessage = $"Added {refs.Count} page(s) from {paths.Count} file(s).";
    }

    public void LoadProject(string path)
    {
        _services.Workspace.OpenProject(path);
        AfterDocumentLoaded();
    }

    public void SaveProjectAs(string path)
    {
        _services.Workspace.SaveProject(path);
        StatusMessage = $"Saved {Path.GetFileName(path)}";
    }

    public ExportResult ExportTo(string path)
    {
        var result = _services.Workspace.ExportPdf(path);
        StatusMessage = result.Warnings.Count == 0
            ? $"Exported to {Path.GetFileName(path)}"
            : $"Exported with {result.Warnings.Count} warning(s).";
        return result;
    }

    public CompressionResult CompressTo(string path, double maxSizeMb, CompressionMode mode)
    {
        var result = _services.Workspace.CompressCurrentDocument(path, maxSizeMb, mode);
        StatusMessage = result.TargetReached
            ? $"Compressed to {result.FinalSizeBytes / 1024.0 / 1024.0:F2} MB."
            : "Could not reach the target size safely.";
        return result;
    }

    private void AfterDocumentLoaded()
    {
        _reportedRenderFailure = false;
        Pages.Clear();
        var document = Session!.Document;
        for (var i = 0; i < document.Pages.Count; i++)
        {
            var pvm = new PageViewModel(i, document.Pages[i]);
            Pages.Add(pvm);
            RequestThumbnail(pvm);
        }

        IsDocumentOpen = Pages.Count > 0;
        UpdatePageDisplaySizes();
        RefreshFileGroups();
        Session.Changed += OnSessionChanged;
        CurrentPageNumber = 1;
        CurrentPage = Pages.FirstOrDefault();
        LoadFooterEditorFromConfig(document.GlobalSettings.FooterConfig);
        RefreshAllPageObjects();
        UpdateAllFooterOverlaysFromDocument();
        StatusMessage = $"Loaded {Pages.Count} page(s).";

        // Every page is visible/navigable in the continuous canvas, but full-resolution bitmaps
        // are requested lazily as pages scroll into view (see RequestVisiblePageBitmaps) rather
        // than all at once — rendering e.g. 100 pages at full DPI simultaneously overwhelms the
        // renderer's throughput and most pages never get a bitmap at all. Request enough of an
        // initial batch here so the top of the document appears immediately; the window's
        // ScrollViewer.ScrollChanged handler (which also fires once layout settles after load)
        // covers the rest, matching the legacy app's viewport-windowed rendering policy.
        foreach (var page in Pages.Take(InitialEagerRenderCount)) RequestPageBitmap(page);
    }

    private const int InitialEagerRenderCount = 6;

    private void OnSessionChanged()
    {
        RefreshAllPageObjects();
        UpdateAllFooterOverlaysFromDocument();
    }

    /// <summary>Call after a page-structure command (delete/move/insert page) — cheap edits go
    /// through <see cref="OnSessionChanged"/> instead.</summary>
    public void RebuildPagesAfterStructureChange()
    {
        var document = Session?.Document;
        if (document is null) return;

        Pages.Clear();
        for (var i = 0; i < document.Pages.Count; i++)
        {
            var pvm = new PageViewModel(i, document.Pages[i]);
            Pages.Add(pvm);
            RequestThumbnail(pvm);
        }
        UpdatePageDisplaySizes();
        RefreshFileGroups();

        CurrentPageNumber = Math.Clamp(CurrentPageNumber, Pages.Count > 0 ? 1 : 0, Math.Max(Pages.Count, 1));
        CurrentPage = Pages.FirstOrDefault(p => p.DisplayNumber == CurrentPageNumber);
        // Rebuilding replaces every PageViewModel; request enough of an initial batch so the
        // document doesn't sit blank until the ScrollViewer's viewport-driven refresh catches up
        // (see RequestVisiblePageBitmaps — same reasoning as AfterDocumentLoaded).
        foreach (var page in Pages.Take(InitialEagerRenderCount)) RequestPageBitmap(page);
        RefreshAllPageObjects();
        UpdateAllFooterOverlaysFromDocument();
    }

    /// <summary>File-level view of the same document the Pages panel shows page by page — one
    /// group per source PDF, in order of first appearance. A file's pages need not be contiguous
    /// after page-level moves; they still group as one file, matching the legacy File Organizer.</summary>
    private void RefreshFileGroups()
    {
        FileGroups.Clear();
        foreach (var group in Pages.GroupBy(p => p.PageRef.SourcePath))
            FileGroups.Add(new FileGroupViewModel { SourcePath = group.Key, PageCount = group.Count(), FirstPage = group.First() });
    }

    /// <summary>Moves every page of <paramref name="fromPath"/> to just before <paramref name="toPath"/>'s
    /// first page — one undo step, reusing <see cref="SetPageOrderCommand"/> rather than a run of
    /// per-page moves (whose intermediate states aren't meaningful to undo into).</summary>
    public void ReorderFileGroup(string fromPath, string toPath)
    {
        if (Session is null || fromPath == toPath) return;
        var moved = new List<int>();
        var rest = new List<int>();
        for (var i = 0; i < Pages.Count; i++)
            (Pages[i].PageRef.SourcePath == fromPath ? moved : rest).Add(i);
        if (moved.Count == 0) return;

        var insertAt = rest.FindIndex(i => Pages[i].PageRef.SourcePath == toPath);
        rest.InsertRange(insertAt < 0 ? rest.Count : insertAt, moved);
        Session.UndoRedo.Push(new SetPageOrderCommand("Reorder file", rest));
        RebuildPagesAfterStructureChange();
    }

    /// <summary>Removes every page belonging to one source file at once — refuses when it's the
    /// only file left, matching the legacy app (use Close/Open a different PDF instead).</summary>
    public void RemoveFileGroup(string path)
    {
        if (Session is null) return;
        if (FileGroups.Count <= 1) { StatusMessage = "Can't remove the only file in this document."; return; }
        var remaining = Enumerable.Range(0, Pages.Count).Where(i => Pages[i].PageRef.SourcePath != path).ToList();
        Session.UndoRedo.Push(new SetPageOrderCommand("Remove file", remaining));
        RebuildPagesAfterStructureChange();
    }

    partial void OnCurrentPageNumberChanged(int value)
    {
        CurrentPage = Pages.FirstOrDefault(p => p.DisplayNumber == value);
    }

    partial void OnCurrentPageChanged(PageViewModel? value)
    {
        foreach (var page in Pages) page.IsCurrent = page == value;
        OnPropertyChanged(nameof(CurrentPageObjects));
        OnPropertyChanged(nameof(FooterOverlay));
    }

    /// <summary>Marks <paramref name="page"/> as current without requiring an object under the
    /// cursor — clicking anywhere on a page (including blank canvas) targets it for Add Text/Add
    /// Image and the footer's "current page" scope, matching the legacy app's page-follows-click
    /// behavior in its continuous canvas.</summary>
    public void SetCurrentPage(PageViewModel page) => CurrentPageNumber = page.DisplayNumber;

    partial void OnZoomChanged(double value)
    {
        UpdatePageDisplaySizes();
        // Don't re-request full-resolution bitmaps for every page here — with many pages that
        // floods the renderer with far more work than it can keep up with (see
        // RequestVisiblePageBitmaps) and most pages end up with no bitmap at all. Each page keeps
        // showing its previous-zoom bitmap (stretched to the new size) until the window's
        // ScrollViewer.ScrollChanged handler — which also fires when zoom changes the content's
        // extent — requests a fresh one for whatever's actually visible.
        foreach (var page in Pages)
            foreach (var obj in page.Objects) obj.SyncFromModel(ScreenScale, page.HeightPt);
        UpdateAllFooterOverlaysFromDocument();
        ZoomPercentText = $"{value * 100:0}%";
    }

    /// <summary>Requests full-resolution bitmaps only for pages currently near the viewport —
    /// called by the window's ScrollViewer.ScrollChanged handler (covers scrolling, zoom, and
    /// initial load, since Avalonia raises that event whenever offset/extent/viewport change).
    /// Matches the legacy app's windowed-rendering policy instead of rendering the whole document
    /// at once, which the renderer's throughput can't keep up with on longer documents.</summary>
    public void RequestVisiblePageBitmaps(IEnumerable<PageViewModel> pages)
    {
        foreach (var page in pages) RequestPageBitmap(page);
    }

    partial void OnFooterFontNameChanged(string value) => UpdateCurrentPageFooterDraftPreview();
    partial void OnFooterFontSizeChanged(double value) => UpdateCurrentPageFooterDraftPreview();
    partial void OnFooterGapPtChanged(double value) => UpdateCurrentPageFooterDraftPreview();
    partial void OnFooterCompressContentChanged(bool value) => UpdateCurrentPageFooterDraftPreview();
    partial void OnFooterShowHeaderChanged(bool value) => UpdateCurrentPageFooterDraftPreview();
    partial void OnFooterShowBordersChanged(bool value) => UpdateCurrentPageFooterDraftPreview();

    [ObservableProperty] private string _zoomPercentText = "100%";

    /// <summary>Parses user-typed zoom text (e.g. "150", "150%") and applies it, or reverts the
    /// text box to the current zoom if the input isn't a usable number.</summary>
    public void CommitZoomPercentText(string text)
    {
        var trimmed = text.Trim().TrimEnd('%');
        if (double.TryParse(trimmed, out var percent) && percent > 0)
            Zoom = Math.Clamp(percent / 100.0, 0.1, 8.0);
        else
            ZoomPercentText = $"{Zoom * 100:0}%";
    }

    /// <summary>Applies a zoom step (e.g. from Ctrl+wheel) while keeping the PDF-space point under
    /// <paramref name="anchorRatio"/> (0..1 fraction of the current page's width/height) stationary
    /// on screen — the caller re-derives the new scroll offset from the pre/post display size.</summary>
    public void ZoomBy(double factor) => Zoom = Math.Clamp(Zoom * factor, 0.1, 8.0);

    private void UpdatePageDisplaySizes()
    {
        foreach (var page in Pages)
        {
            page.DisplayWidth = page.WidthPt * ScreenScale;
            page.DisplayHeight = page.HeightPt * ScreenScale;
        }
    }

    /// <summary>Full-resolution bitmap for a page's canvas — requested for every page so the whole
    /// document stays visible, not just whichever page is "current".</summary>
    private void RequestPageBitmap(PageViewModel page)
    {
        var bitmap = _services.BitmapCache.TryGet(page.PageRef.SourcePath, page.PageRef.SourceIndex, RenderDpi);
        if (bitmap is not null)
        {
            page.Bitmap = ToAvaloniaBitmap(bitmap);
        }
        else
        {
            _services.BitmapCache.RequestAsync(page.PageRef.SourcePath, page.PageRef.SourceIndex, RenderDpi);
        }
    }

    /// <summary>Low-DPI bitmap for the page-list sidebar — cheap enough to request for every page
    /// up front, independent of zoom.</summary>
    private void RequestThumbnail(PageViewModel page)
    {
        var dpi = PdfPageRasterRenderer.ThumbnailDpi;
        var bitmap = _services.BitmapCache.TryGet(page.PageRef.SourcePath, page.PageRef.SourceIndex, dpi);
        if (bitmap is not null)
        {
            page.ThumbnailBitmap = ToAvaloniaBitmap(bitmap);
        }
        else
        {
            _services.BitmapCache.RequestAsync(page.PageRef.SourcePath, page.PageRef.SourceIndex, dpi);
        }
    }

    private void OnBitmapReady(PageBitmapReadyArgs args)
    {
        var page = Pages.FirstOrDefault(p => p.PageRef.SourcePath == args.SourcePath && p.PageRef.SourceIndex == args.PageIndex);
        if (page is null) return;

        var bitmap = _services.BitmapCache.TryGet(args.SourcePath, args.PageIndex, args.Dpi);
        if (bitmap is null) return;
        var avaloniaBitmap = ToAvaloniaBitmap(bitmap);

        if (Math.Abs(args.Dpi - PdfPageRasterRenderer.ThumbnailDpi) < 0.01)
            Dispatcher.UIThread.Post(() => page.ThumbnailBitmap = avaloniaBitmap);
        else if (Math.Abs(args.Dpi - RenderDpi) < 0.01)
            Dispatcher.UIThread.Post(() => page.Bitmap = avaloniaBitmap);
    }

    private static Bitmap ToAvaloniaBitmap(SkiaSharp.SKBitmap skBitmap)
    {
        using var image = SkiaSharp.SKImage.FromBitmap(skBitmap);
        using var data = image.Encode(SkiaSharp.SKEncodedImageFormat.Png, 90);
        using var stream = new MemoryStream(data.ToArray());
        return new Bitmap(stream);
    }

    /// <summary>Rebuilds every page's <see cref="PageViewModel.Objects"/> from the document model —
    /// called after any change (add/delete/move/undo/redo), for every page, not just the current
    /// one, so an object stays visible on its page regardless of which page is "current".</summary>
    private void RefreshAllPageObjects()
    {
        if (Session is null) return;
        var selectedId = SelectedObject?.Id;

        foreach (var page in Pages)
        {
            var config = Session.Document.GetPageConfig(page.DisplayNumber);
            page.Objects.Clear();
            foreach (var obj in config.Objects.Where(o => o.Visible).OrderBy(o => o.ZIndex))
            {
                var ovm = new ObjectViewModel(obj) { OwnerPage = page };
                ovm.SyncFromModel(ScreenScale, page.HeightPt);
                ovm.IsSelected = selectedId == obj.Id;
                if (obj is ImagePageObject) LoadImageBitmapAsync(ovm);
                page.Objects.Add(ovm);
            }
        }

        SelectedObject = selectedId is null ? null : Pages.SelectMany(p => p.Objects).FirstOrDefault(o => o.Id == selectedId);
        OnPropertyChanged(nameof(CurrentPageObjects));
    }

    private static void LoadImageBitmapAsync(ObjectViewModel ovm)
    {
        var path = ovm.ImagePath;
        if (path is null || !File.Exists(path)) return;
        Task.Run(() =>
        {
            try
            {
                using var stream = File.OpenRead(path);
                var bitmap = new Bitmap(stream);
                Dispatcher.UIThread.Post(() => ovm.ImageBitmap = bitmap);
            }
            catch (Exception)
            {
                // Missing/corrupt image — leave the placeholder, matches export's own skip-not-abort policy.
            }
        });
    }

    /// <summary>Selects one object (or clears selection) across the whole document — also makes
    /// the object's own page current, since selection/editing follows whichever page the user
    /// actually clicked, not a separate "current page" the user has to switch to first.</summary>
    public void SelectObject(ObjectViewModel? obj)
    {
        foreach (var page in Pages)
            foreach (var o in page.Objects) o.IsSelected = false;

        if (obj is not null)
        {
            obj.IsSelected = true;
            if (obj.OwnerPage is not null) CurrentPageNumber = obj.OwnerPage.DisplayNumber;
        }
        SelectedObject = obj;
        Session?.Select(obj is null ? [] : [obj.Id]);
    }

    /// <summary>Call when a select/move/resize/rotate gesture starts on a page's canvas — the
    /// canvas mutates the object live for immediate visual feedback; this only records the
    /// "before" snapshot and selects the object.</summary>
    public void BeginGesture(ObjectViewModel obj)
    {
        SelectObject(obj);
        _dragObject = obj;
        _dragStart = ObjectSnapshot.Of(obj.Model);
    }

    public void EndGesture()
    {
        if (_dragObject is null || _dragStart is null || Session is null) { _dragObject = null; _dragStart = null; return; }
        var after = ObjectSnapshot.Of(_dragObject.Model);
        if (!after.Equals(_dragStart.Value))
            Session.ApplyStateChange("Transform object", [(_dragObject.Id, _dragStart.Value, after)]);
        _dragObject = null;
        _dragStart = null;
    }

    public void AddTextToCurrentPage()
    {
        var page = CurrentPage;
        if (page is null || Session is null) return;
        var style = new TextStyle { Text = "New text", FontName = _services.FontRegistry.FallbackFontName ?? "Arial", FontSize = 18 };
        var newId = Session.AddText(CurrentPageNumber, x: 72, y: page.HeightPt - 144, width: 200, height: 30, style);
        SelectObject(page.Objects.FirstOrDefault(o => o.Id == newId));
    }

    public void AddImageToCurrentPage(string imagePath)
    {
        var page = CurrentPage;
        if (page is null || Session is null) return;
        using var bitmap = SkiaSharp.SKBitmap.Decode(imagePath);
        var aspect = bitmap is { Width: > 0, Height: > 0 } ? (double)bitmap.Height / bitmap.Width : 1.0;
        const double displayWidth = 150.0;
        var newId = Session.AddImage(CurrentPageNumber, imagePath, x: 72, y: page.HeightPt - 72 - displayWidth * aspect, displayWidth, displayWidth * aspect);
        SelectObject(page.Objects.FirstOrDefault(o => o.Id == newId));
    }

    public void DeleteSelected()
    {
        Session?.DeleteSelected();
        SelectedObject = null;
    }

    public void BringSelectedToFront()
    {
        if (SelectedObject is not { } obj || Session is null || CurrentPageObjects.Count == 0) return;
        var maxZ = CurrentPageObjects.Max(o => o.Model.ZIndex);
        if (obj.Model.ZIndex > maxZ) return;
        var before = ObjectSnapshot.Of(obj.Model);
        Session.ApplyStateChange("Bring to front", [(obj.Id, before, before with { ZIndex = maxZ + 1 })]);
    }

    public void SendSelectedToBack()
    {
        if (SelectedObject is not { } obj || Session is null || CurrentPageObjects.Count == 0) return;
        var minZ = CurrentPageObjects.Min(o => o.Model.ZIndex);
        if (obj.Model.ZIndex < minZ) return;
        var before = ObjectSnapshot.Of(obj.Model);
        Session.ApplyStateChange("Send to back", [(obj.Id, before, before with { ZIndex = minZ - 1 })]);
    }

    public void DuplicateSelected()
    {
        if (SelectedObject is not { } obj || Session is null) return;
        var clone = obj.Model.Clone();
        clone.X += 10;
        clone.Y -= 10;
        var command = new PasteObjectsCommand(CurrentPageNumber, [clone]);
        Session.UndoRedo.Push(command);
        var newId = command.PastedObjectIds.FirstOrDefault();
        if (newId is not null) SelectObject(CurrentPageObjects.FirstOrDefault(o => o.Id == newId));
    }

    private PageObject? _clipboardObject;

    /// <summary>True once something is on the internal clipboard — drives the enabled state of
    /// the toolbar's Paste icon so copy/paste isn't keyboard-shortcut-only.</summary>
    public bool HasClipboardContent => _clipboardObject is not null;

    public void CopySelected()
    {
        if (SelectedObject is not { } obj) return;
        _clipboardObject = obj.Model.Clone();
        OnPropertyChanged(nameof(HasClipboardContent));
        StatusMessage = "Copied. Switch page if you like, then paste (Ctrl+V or the Paste button).";
    }

    /// <summary>Pastes onto whatever page is current now, offset — unlike Duplicate (always an
    /// offset copy on the same page), this is how a stamp/text box gets carried from one page to
    /// another.</summary>
    public void PasteObject()
    {
        if (_clipboardObject is null || Session is null || CurrentPage is null) return;
        var clone = _clipboardObject.Clone();
        clone.X += 10;
        clone.Y -= 10;
        var command = new PasteObjectsCommand(CurrentPageNumber, [clone]);
        Session.UndoRedo.Push(command);
        var newId = command.PastedObjectIds.FirstOrDefault();
        if (newId is not null) SelectObject(CurrentPageObjects.FirstOrDefault(o => o.Id == newId));
    }

    /// <summary>Pastes at the exact copied coordinates on whatever page is current — matches the
    /// legacy app's "Paste in Place" (as opposed to the default offset paste).</summary>
    public void PasteObjectInPlace()
    {
        if (_clipboardObject is null || Session is null || CurrentPage is null) return;
        var clone = _clipboardObject.Clone();
        var command = new PasteObjectsCommand(CurrentPageNumber, [clone]);
        Session.UndoRedo.Push(command);
        var newId = command.PastedObjectIds.FirstOrDefault();
        if (newId is not null) SelectObject(CurrentPageObjects.FirstOrDefault(o => o.Id == newId));
    }

    public void Undo()
    {
        var command = Session?.Undo();
        if (command?.AffectsPageStructure == true) RebuildPagesAfterStructureChange();
    }

    public void Redo()
    {
        var command = Session?.Redo();
        if (command?.AffectsPageStructure == true) RebuildPagesAfterStructureChange();
    }

    public void ZoomIn() => Zoom = Math.Min(8.0, Zoom * 1.25);
    public void ZoomOut() => Zoom = Math.Max(0.1, Zoom / 1.25);
    public void ZoomReset() => Zoom = 1.0;

    public bool ShowDocument => IsDocumentOpen;

    public void GoToPage(int pageNumber)
    {
        if (pageNumber >= 1 && pageNumber <= Pages.Count) CurrentPageNumber = pageNumber;
    }

    /// <summary>Moves the page at 0-based <paramref name="fromIndex"/> to just before the page
    /// currently at 0-based <paramref name="toIndex"/> — one undo step.</summary>
    public void ReorderPage(int fromIndex, int toIndex)
    {
        if (Session is null || fromIndex == toIndex || fromIndex < 0 || toIndex < 0) return;
        if (fromIndex >= Pages.Count || toIndex >= Pages.Count) return;

        var order = Enumerable.Range(0, Pages.Count).ToList();
        order.Remove(fromIndex);
        var insertAt = order.IndexOf(toIndex);
        order.Insert(insertAt < 0 ? order.Count : insertAt, fromIndex);

        Session.UndoRedo.Push(new SetPageOrderCommand("Reorder pages", order));
        RebuildPagesAfterStructureChange();
    }

    public void DeletePage(int pageIndex)
    {
        if (Session is null || pageIndex < 0 || pageIndex >= Pages.Count) return;
        Session.UndoRedo.Push(new DeletePageCommand(pageIndex));
        RebuildPagesAfterStructureChange();
    }

    [ObservableProperty] private string _footerRangeText = "";
    [ObservableProperty] private FooterApplyScope _footerApplyScope = FooterApplyScope.All;

    public bool IsFooterScopeAll => FooterApplyScope == FooterApplyScope.All;
    public bool IsFooterScopeSelected => FooterApplyScope == FooterApplyScope.Selected;
    public bool IsFooterScopeRange => FooterApplyScope == FooterApplyScope.Range;

    partial void OnFooterApplyScopeChanged(FooterApplyScope value)
    {
        OnPropertyChanged(nameof(IsFooterScopeAll));
        OnPropertyChanged(nameof(IsFooterScopeSelected));
        OnPropertyChanged(nameof(IsFooterScopeRange));
    }

    private PageViewModel? _selectionAnchor;

    /// <summary>Ctrl-click a thumbnail: toggle it into/out of the "Selected pages" footer scope.</summary>
    public void TogglePageSelection(PageViewModel page)
    {
        page.IsSelected = !page.IsSelected;
        _selectionAnchor = page;
    }

    /// <summary>Shift-click a thumbnail: select every page between the last-touched one and this one.</summary>
    public void SelectPageRange(PageViewModel target)
    {
        var anchor = _selectionAnchor ?? CurrentPage;
        var fromIndex = anchor is null ? -1 : Pages.IndexOf(anchor);
        var toIndex = Pages.IndexOf(target);
        if (fromIndex < 0 || toIndex < 0) { target.IsSelected = true; return; }
        var lo = Math.Min(fromIndex, toIndex);
        var hi = Math.Max(fromIndex, toIndex);
        for (var i = lo; i <= hi; i++) Pages[i].IsSelected = true;
    }

    /// <summary>Dispatches to whichever scope is currently selected — matches the legacy Quick
    /// Footer panel's single "Apply Footer" button driven by an All/Selected/Range segmented
    /// control, rather than one button per scope.</summary>
    public void ApplyFooter()
    {
        switch (FooterApplyScope)
        {
            case FooterApplyScope.Selected:
                var selected = Pages.Where(p => p.IsSelected).Select(p => p.DisplayNumber).ToList();
                if (selected.Count == 0)
                {
                    StatusMessage = "No pages selected. Ctrl/Shift-click thumbnails to select pages.";
                    return;
                }
                ApplyFooter(selected);
                StatusMessage = $"Footer applied to {selected.Count} selected page(s).";
                break;
            case FooterApplyScope.Range:
                ApplyFooterToRange();
                break;
            default:
                ApplyFooterToAllPages();
                StatusMessage = $"Footer applied to all {Pages.Count} page(s).";
                break;
        }
    }

    public void ApplyFooterToCurrentPage() => ApplyFooter(new[] { CurrentPageNumber });

    public void ApplyFooterToAllPages() => ApplyFooter(Enumerable.Range(1, Pages.Count));

    /// <summary>Applies the footer only to the typed range ("1-3, 7" or "all") — matching the
    /// legacy Quick Footer panel's "Page range" apply scope. Refuses to guess on a bad range,
    /// same as the legacy panel: it reports the problem instead of silently applying to everything.</summary>
    public void ApplyFooterToRange()
    {
        if (Session is null) return;
        try
        {
            var pageNumbers = PageRangeParser.Parse(FooterRangeText, Pages.Count);
            ApplyFooter(pageNumbers);
            StatusMessage = $"Footer applied to {pageNumbers.Count} page(s) ({FooterRangeText}).";
        }
        catch (FormatException ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private void ApplyFooter(IEnumerable<int> pageNumbers)
    {
        if (Session is null) return;
        var config = BuildFooterConfigFromEditor();
        Session.UndoRedo.Push(new ChangeFooterCommand("Apply footer", pageNumbers, config));
        // OnSessionChanged (via Session.Changed) already refreshes every page's overlay from the
        // document, so every applicable page shows the footer immediately — not just the current one.
    }

    private FooterConfig BuildFooterConfigFromEditor() => new()
    {
        Enabled = true,
        Table = new FooterTable
        {
            Columns = FooterColumns.Select(c => new FooterColumnDef { Header = c.Header, WidthPt = c.WidthPt, Align = c.Align }).ToArray(),
            Rows = FooterRows.Select(r => new FooterRow { Cells = r.Cells.Select(c => c.Text).ToArray() }).ToArray(),
            ShowHeader = FooterShowHeader,
            ShowBorders = FooterShowBorders,
        },
        FontName = FooterFontName,
        FontSize = FooterFontSize,
        ContentGapPt = FooterGapPt,
        CompressContent = FooterCompressContent,
    };

    /// <summary>Recomputes every page's footer overlay from what's actually applied to it in the
    /// document model (<see cref="EditorDocument.GetPageConfig"/>) — this is the same config
    /// <see cref="Pdf.Export.DocumentExporter"/> reads, so the on-screen preview and the exported
    /// PDF always agree, for every page, not just the one being edited.</summary>
    private void UpdateAllFooterOverlaysFromDocument()
    {
        if (Session is null) return;
        foreach (var page in Pages)
        {
            var config = Session.Document.GetPageConfig(page.DisplayNumber).FooterConfig;
            ComputeFooterOverlay(page, config);
        }
    }

    /// <summary>While the footer panel is being edited (before "Apply"), only the current page
    /// previews the in-progress draft — every other page keeps showing its own actually-applied
    /// footer, so the preview never lies about pages that weren't targeted.</summary>
    private void UpdateCurrentPageFooterDraftPreview()
    {
        if (CurrentPage is not { } page) return;
        ComputeFooterOverlay(page, BuildFooterConfigFromEditor());
    }

    private void ComputeFooterOverlay(PageViewModel page, FooterConfig config)
    {
        if (Session is null) { page.FooterOverlay.Visible = false; return; }

        var preview = _services.FooterPreview.Compute(
            page.PageRef.SourcePath, page.PageRef.SourceIndex, page.WidthPt, page.HeightPt,
            config, page.DisplayNumber, Pages.Count);

        var overlay = page.FooterOverlay;
        if (!preview.HasFooter)
        {
            overlay.Visible = false;
            return;
        }

        var scale = ScreenScale;
        var table = preview.Table;
        var tableTopWorld = preview.Placement.BottomMarginPt + table.TotalHeight;
        const double ascentRatio = 0.8; // must match TextLayoutEngine's ascent approximation

        var lines = new List<FooterLineViewModel>();
        foreach (var row in table.Rows)
        {
            var rowTopWorld = tableTopWorld - row.Top;
            foreach (var cell in row.Cells)
            {
                foreach (var line in cell.Text.Lines)
                {
                    if (line.Text.Length == 0) continue;
                    var worldTopY = rowTopWorld - (line.BaselineFromTop - config.FontSize * ascentRatio);
                    lines.Add(new FooterLineViewModel(
                        line.Text, (cell.Left + line.X) * scale, (page.HeightPt - worldTopY) * scale,
                        config.FontName, config.FontSize * scale));
                }
            }
        }

        // WYSIWYG with export: solid borders only, no dashed "will this page get compressed"
        // editor affordance — the preview must show exactly what will be exported, nothing else.
        var gridLines = new List<FooterGridSegment>();
        if (config.Table.ShowBorders && table.ColumnLefts.Count > 0)
        {
            var tableLeft = table.ColumnLefts[0] * scale;
            var tableRight = (table.ColumnLefts[^1] + table.ColumnWidths[^1]) * scale;
            var screenTop = (page.HeightPt - tableTopWorld) * scale;
            var screenBottom = (page.HeightPt - preview.Placement.BottomMarginPt) * scale;

            gridLines.Add(new FooterGridSegment(tableLeft, screenTop, tableRight, screenTop));
            gridLines.Add(new FooterGridSegment(tableLeft, screenBottom, tableRight, screenBottom));
            gridLines.Add(new FooterGridSegment(tableLeft, screenTop, tableLeft, screenBottom));
            gridLines.Add(new FooterGridSegment(tableRight, screenTop, tableRight, screenBottom));

            var y = tableTopWorld;
            for (var i = 0; i < table.Rows.Count - 1; i++)
            {
                y -= table.Rows[i].Height;
                var screenY = (page.HeightPt - y) * scale;
                gridLines.Add(new FooterGridSegment(tableLeft, screenY, tableRight, screenY));
            }

            for (var i = 1; i < table.ColumnLefts.Count; i++)
            {
                var x = table.ColumnLefts[i] * scale;
                gridLines.Add(new FooterGridSegment(x, screenTop, x, screenBottom));
            }
        }

        overlay.Visible = true;
        overlay.ContentCompressed = preview.Placement.ContentCompressed;
        overlay.ZoneTop = (page.HeightPt - preview.Placement.BottomMarginPt - table.TotalHeight) * scale;
        overlay.ZoneHeight = table.TotalHeight * scale;
        overlay.Lines = lines.ToArray();
        overlay.GridLines = gridLines.ToArray();
    }
}
