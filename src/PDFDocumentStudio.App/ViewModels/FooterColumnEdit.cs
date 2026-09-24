using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.App.ViewModels;

/// <summary>Matches the legacy Quick Footer panel's "Apply to" segmented control.</summary>
public enum FooterApplyScope { All, Selected, Range }

/// <summary>One footer column: a real semantic column (e.g. "Name", "Designation") with its own
/// width and text alignment — not a generic "Col N".</summary>
public sealed partial class FooterColumnEdit : ObservableObject
{
    /// <summary>1-based position, kept current by <c>MainViewModel</c> — only for numbering new
    /// columns by default, not persisted (column order in the list IS the order).</summary>
    [ObservableProperty] private int _displayNumber;
    [ObservableProperty] private string _header = string.Empty;

    /// <summary>Explicit width in points, or null to share the remaining width equally with other
    /// auto-width columns.</summary>
    [ObservableProperty] private double? _widthPt;

    [ObservableProperty] private FooterCellAlign _align = FooterCellAlign.Center;
}

/// <summary>One cell's text within a <see cref="FooterRowEdit"/>, positionally matched to a
/// <see cref="FooterColumnEdit"/> by index.</summary>
public sealed partial class FooterCellEdit : ObservableObject
{
    [ObservableProperty] private string _text = string.Empty;
}

/// <summary>One data row underneath the column headers — the footer table can have any number of
/// rows, not a fixed "Line 1 / Line 2" pair.</summary>
public sealed partial class FooterRowEdit : ObservableObject
{
    public ObservableCollection<FooterCellEdit> Cells { get; } = [];
}
