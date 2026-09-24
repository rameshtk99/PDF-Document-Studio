using PDFDocumentStudio.Pdf.Compression;
using PdfSharp.Pdf.IO;

namespace PDFDocumentStudio.Tests.Pdf;

[Collection("Pdf")]
public class PdfCompressorTests(PdfTestFixture fixture)
{
    [Fact]
    public void Compress_NeverGrowsFileOrChangesPageCount()
    {
        var output = Path.Combine(Path.GetTempPath(), $"compress_test_{Guid.NewGuid():N}.pdf");
        try
        {
            var result = new PdfCompressor().Compress(fixture.SamplePdfPath, output, maxSizeMb: 50, CompressionMode.Balanced);
            Assert.True(result.FinalSizeBytes <= result.OriginalSizeBytes || result.FinalSizeBytes == new FileInfo(fixture.SamplePdfPath).Length);

            using var original = PdfReader.Open(fixture.SamplePdfPath, PdfDocumentOpenMode.Import);
            using var compressed = PdfReader.Open(output, PdfDocumentOpenMode.Import);
            Assert.Equal(original.PageCount, compressed.PageCount);
        }
        finally { if (File.Exists(output)) File.Delete(output); }
    }

    [Fact]
    public void Compress_LosslessMode_NeverRecompressesImages()
    {
        var output = Path.Combine(Path.GetTempPath(), $"compress_lossless_{Guid.NewGuid():N}.pdf");
        try
        {
            var result = new PdfCompressor().Compress(fixture.SamplePdfPath, output, maxSizeMb: 0.001, CompressionMode.Lossless);
            Assert.Single(result.Notes); // only the structural-resave note — no quality-ladder rungs attempted
        }
        finally { if (File.Exists(output)) File.Delete(output); }
    }

    [Fact]
    public void Compress_AlreadyUnderTarget_ReportsTargetReached()
    {
        var output = Path.Combine(Path.GetTempPath(), $"compress_easy_{Guid.NewGuid():N}.pdf");
        try
        {
            var result = new PdfCompressor().Compress(fixture.SamplePdfPath, output, maxSizeMb: 100, CompressionMode.Balanced);
            Assert.True(result.TargetReached);
        }
        finally { if (File.Exists(output)) File.Delete(output); }
    }
}
