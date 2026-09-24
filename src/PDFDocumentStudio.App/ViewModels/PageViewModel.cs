using System.Collections.ObjectModel;
using Avalonia.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.App.ViewModels;

/// <summary>One page in the continuous document view. Every page is always visible and fully
/// interactive — it owns its own footer preview and object list rather than sharing a single
/// "current page only" canvas, which is what used to make footers/text/images appear on only one
/// page at a time.</summary>
public sealed partial class PageViewModel(int pageIndex, PageRef pageRef) : ObservableObject
{
    public int PageIndex { get; } = pageIndex;
    public int DisplayNumber => PageIndex + 1;
    public PageRef PageRef { get; } = pageRef;

    [ObservableProperty] private double _widthPt = pageRef.Width;
    [ObservableProperty] private double _heightPt = pageRef.Height;
    [ObservableProperty] private double _displayWidth = pageRef.Width;
    [ObservableProperty] private double _displayHeight = pageRef.Height;
    [ObservableProperty] private Bitmap? _bitmap;
    [ObservableProperty] private Bitmap? _thumbnailBitmap;
    [ObservableProperty] private bool _isCurrent;

    /// <summary>Multi-select for the "Selected pages" footer-apply scope — Ctrl/Shift-click in the
    /// Pages panel, independent of <see cref="IsCurrent"/>.</summary>
    [ObservableProperty] private bool _isSelected;

    /// <summary>This page's own overlay objects (text/images) — kept in sync with the document
    /// model for every page, not just whichever one is "current".</summary>
    public ObservableCollection<ObjectViewModel> Objects { get; } = [];

    /// <summary>This page's own footer preview — reflects the footer actually applied to this
    /// page in the document model, so every applicable page shows it, matching the export.</summary>
    public FooterOverlayViewModel FooterOverlay { get; } = new();
}
