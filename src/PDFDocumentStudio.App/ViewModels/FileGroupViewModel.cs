namespace PDFDocumentStudio.App.ViewModels;

/// <summary>One source PDF's pages within the combined document — the File Organizer's unit,
/// matching the legacy app's file-level view of the same document the Pages panel shows page by
/// page. A file's pages need not be contiguous; this just reports the current grouping.</summary>
public sealed class FileGroupViewModel
{
    public required string SourcePath { get; init; }
    public string FileName => System.IO.Path.GetFileName(SourcePath);
    public required int PageCount { get; init; }
    public required PageViewModel FirstPage { get; init; }
}
