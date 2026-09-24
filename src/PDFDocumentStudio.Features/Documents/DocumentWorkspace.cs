using PDFDocumentStudio.Features.Editing;
using PDFDocumentStudio.Pdf.Compression;
using PDFDocumentStudio.Pdf.Export;
using PDFDocumentStudio.Pdf.Loading;
using PDFDocumentStudio.Core.Serialization;

namespace PDFDocumentStudio.Features.Documents;

/// <summary>Open/save/export orchestration: wires <see cref="PdfLoader"/>, <see cref="ProjectSerializer"/>,
/// <see cref="DocumentExporter"/>, and <see cref="PdfCompressor"/> around the current <see cref="EditorSession"/>.</summary>
public sealed class DocumentWorkspace(
    PdfLoader pdfLoader, ProjectSerializer projectSerializer, DocumentExporter exporter, PdfCompressor compressor)
{
    public EditorSession? Session { get; private set; }
    public string? ProjectPath { get; private set; }

    public event Action? DocumentChanged;

    public void OpenPdf(string path) => SetSession(pdfLoader.LoadPdf(path), projectPath: null);

    public void OpenPdfs(IReadOnlyList<string> paths) => SetSession(pdfLoader.LoadPdfs(paths), projectPath: null);

    public void OpenProject(string path) => SetSession(projectSerializer.Load(path), projectPath: path);

    public void SaveProject(string path)
    {
        RequireSession();
        projectSerializer.Save(Session!.Document, path);
        ProjectPath = path;
    }

    public ExportResult ExportPdf(string outputPath)
    {
        RequireSession();
        return exporter.Export(Session!.Document, outputPath);
    }

    /// <summary>Exports the current edits to a temp file first, then compresses that — compression
    /// always operates on a fully-baked export, never the source PDF directly.</summary>
    public CompressionResult CompressCurrentDocument(string outputPath, double maxSizeMb, CompressionMode mode)
    {
        RequireSession();
        var temp = Path.Combine(Path.GetTempPath(), $"pdfstudio_export_{Guid.NewGuid():N}.pdf");
        try
        {
            exporter.Export(Session!.Document, temp);
            return compressor.Compress(temp, outputPath, maxSizeMb, mode);
        }
        finally
        {
            if (File.Exists(temp)) File.Delete(temp);
        }
    }

    private void SetSession(Core.Model.EditorDocument document, string? projectPath)
    {
        Session = new EditorSession(document);
        ProjectPath = projectPath;
        DocumentChanged?.Invoke();
    }

    private void RequireSession()
    {
        if (Session is null) throw new InvalidOperationException("No document is open.");
    }
}
