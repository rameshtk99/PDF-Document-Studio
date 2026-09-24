using PDFDocumentStudio.Core.Interfaces;
using PDFDocumentStudio.Core.Model;
using PdfSharp.Pdf.IO;

namespace PDFDocumentStudio.Pdf.Loading;

/// <summary>
/// Opens PDF files and builds the <see cref="EditorDocument"/>/<see cref="PageRef"/> structures
/// Core works with. Implements <see cref="IPageMetadataResolver"/> so Core's project-migration
/// code can synthesize a page manifest for a legacy v1.0 project without Core depending on a PDF
/// library. See docs/LEGACY_FEATURE_INVENTORY.md §2.
/// </summary>
public sealed class PdfLoader : IPageMetadataResolver
{
    private static readonly byte[] PdfMagic = "%PDF"u8.ToArray();

    public static bool IsValidPdf(string path)
    {
        if (!File.Exists(path)) return false;
        using var stream = File.OpenRead(path);
        var header = new byte[PdfMagic.Length];
        var read = stream.Read(header, 0, header.Length);
        return read == PdfMagic.Length && header.AsSpan().SequenceEqual(PdfMagic);
    }

    public IReadOnlyList<PageRef> BuildPageRefs(string pdfPath)
    {
        using var document = PdfReader.Open(pdfPath, PdfDocumentOpenMode.Import);
        var refs = new List<PageRef>(document.PageCount);
        for (var i = 0; i < document.PageCount; i++)
        {
            var page = document.Pages[i];
            refs.Add(new PageRef
            {
                SourcePath = pdfPath,
                SourceIndex = i,
                Width = page.Width.Point,
                Height = page.Height.Point,
                Rotation = page.Rotate,
            });
        }
        return refs;
    }

    /// <summary>Loads a single PDF as a brand-new editing document.</summary>
    public EditorDocument LoadPdf(string path)
    {
        if (!IsValidPdf(path))
            throw new InvalidDataException($"'{path}' is not a valid PDF file (missing %PDF header).");

        var document = new EditorDocument { PrimaryPath = path };
        document.Pages.AddRange(BuildPageRefs(path));
        return document;
    }

    /// <summary>Combines several PDFs into one editing document — each page keeps a reference to
    /// its own source file; no page bytes are copied. The first file supplies the document's
    /// primary/display identity.</summary>
    public EditorDocument LoadPdfs(IReadOnlyList<string> paths)
    {
        if (paths.Count == 0) throw new ArgumentException("At least one PDF path is required.", nameof(paths));

        var document = new EditorDocument { PrimaryPath = paths[0] };
        foreach (var path in paths)
        {
            if (!IsValidPdf(path))
                throw new InvalidDataException($"'{path}' is not a valid PDF file (missing %PDF header).");
            document.Pages.AddRange(BuildPageRefs(path));
        }
        return document;
    }
}
