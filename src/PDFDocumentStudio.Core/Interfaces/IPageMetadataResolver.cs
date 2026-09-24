using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Core.Interfaces;

/// <summary>
/// Reads page count/size/rotation from a PDF file to build its <see cref="PageRef"/> list. Kept as
/// a Core-owned abstraction (implemented in the Pdf layer with PDFsharp) so migrating an old
/// project file that lacks an explicit page manifest — legacy version "1.0", see
/// docs/LEGACY_FEATURE_INVENTORY.md §1 — can synthesize one without Core taking a dependency on a
/// PDF library.
/// </summary>
public interface IPageMetadataResolver
{
    IReadOnlyList<PageRef> BuildPageRefs(string pdfPath);
}
