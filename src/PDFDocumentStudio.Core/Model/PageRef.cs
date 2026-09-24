namespace PDFDocumentStudio.Core.Model;

/// <summary>
/// Stable identity of one physical PDF page, decoupled from its display position in the document.
/// Surviving reorder/delete/insert by id is what lets a document combine pages from multiple source
/// files (or reorder its own pages) without ever copying page bytes — content is read lazily from
/// <see cref="SourcePath"/>/<see cref="SourceIndex"/> at render/export time.
/// </summary>
public sealed class PageRef
{
    public string Id { get; init; } = Guid.NewGuid().ToString();

    /// <summary>Absolute path of the PDF file this page's content actually lives in.</summary>
    public required string SourcePath { get; set; }

    /// <summary>0-based page index within <see cref="SourcePath"/>.</summary>
    public required int SourceIndex { get; set; }

    /// <summary>Page width in PDF points, cached from the source at load time.</summary>
    public required double Width { get; set; }

    /// <summary>Page height in PDF points, cached from the source at load time.</summary>
    public required double Height { get; set; }

    /// <summary>The page's /Rotate value (0/90/180/270) as read from the source PDF.</summary>
    public int Rotation { get; set; }

    public PageRef Clone() => new()
    {
        Id = Id,
        SourcePath = SourcePath,
        SourceIndex = SourceIndex,
        Width = Width,
        Height = Height,
        Rotation = Rotation,
    };
}
