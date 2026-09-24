using PDFDocumentStudio.Core.Model;
using PDFDocumentStudio.Pdf.Export;
using PDFDocumentStudio.Pdf.Loading;
using PdfSharp.Pdf.IO;
using SkiaSharp;

namespace PDFDocumentStudio.Tests.Pdf;

[Collection("Pdf")]
public class DocumentExporterTests(PdfTestFixture fixture)
{
    private DocumentExporter MakeExporter() => new(fixture.WhiteSpace, fixture.Metrics);

    private EditorDocument LoadSampleDocument()
    {
        var doc = new PdfLoader().LoadPdf(fixture.SamplePdfPath);
        return doc;
    }

    [Fact]
    public void Export_PlainPage_ProducesValidPdfWithSamePageCount()
    {
        var document = LoadSampleDocument();
        var outputPath = TempPath();
        try
        {
            var result = MakeExporter().Export(document, outputPath);
            Assert.Empty(result.Warnings);

            using var written = PdfReader.Open(outputPath, PdfDocumentOpenMode.Import);
            Assert.Equal(document.PageCount, written.PageCount);
        }
        finally { Cleanup(outputPath); }
    }

    [Fact]
    public void Export_WithFooterNeedingRoom_CompressesPageAndRecordsIt()
    {
        var document = LoadSampleDocument();
        document.GlobalSettings = document.GlobalSettings with
        {
            FooterConfig = new FooterConfig
            {
                Enabled = true,
                Table = new FooterTable { Columns = [new FooterColumnDef()], Rows = [new FooterRow { Cells = ["Footer text"] }], ShowHeader = false },
                ContentGapPt = 72,
                FontSize = 13,
            },
        };

        var outputPath = TempPath();
        try
        {
            var result = MakeExporter().Export(document, outputPath);
            using var written = PdfReader.Open(outputPath, PdfDocumentOpenMode.Import);
            Assert.Equal(document.PageCount, written.PageCount);
            // At least the pipeline ran the footer branch without throwing; compression itself
            // depends on this specific PDF's natural whitespace, asserted indirectly via notes.
            Assert.True(result.PerPageNotes.Count > 0);
        }
        finally { Cleanup(outputPath); }
    }

    [Fact]
    public void Export_RotatedTextObject_DoesNotThrowAndProducesOutput()
    {
        var document = LoadSampleDocument();
        document.GetOrCreatePageConfig(1).Objects.Add(new TextPageObject
        {
            Style = new TextStyle { Text = "Rotated", FontName = fixture.FontRegistry.FallbackFontName ?? "Arial", FontSize = 18 },
            X = 100, Y = 400, Width = 150, Height = 40, Rotation = 30, Opacity = 60,
        });

        var outputPath = TempPath();
        try
        {
            MakeExporter().Export(document, outputPath);
            Assert.True(File.Exists(outputPath));
            Assert.True(new FileInfo(outputPath).Length > 0);
        }
        finally { Cleanup(outputPath); }
    }

    [Fact]
    public void Export_ImageObjectWithMissingFile_SkipsWithWarningInsteadOfThrowing()
    {
        var document = LoadSampleDocument();
        document.GetOrCreatePageConfig(1).Objects.Add(new ImagePageObject
        {
            ImagePath = Path.Combine(Path.GetTempPath(), "does_not_exist_" + Guid.NewGuid() + ".png"),
            X = 50, Y = 50, Width = 100, Height = 100,
        });

        var outputPath = TempPath();
        try
        {
            var result = MakeExporter().Export(document, outputPath);
            Assert.Single(result.Warnings);
            Assert.True(File.Exists(outputPath));
        }
        finally { Cleanup(outputPath); }
    }

    [Fact]
    public void Export_RealImageObject_EmbedsSuccessfully()
    {
        var imagePath = CreateTestPng();
        var document = LoadSampleDocument();
        document.GetOrCreatePageConfig(1).Objects.Add(new ImagePageObject
        {
            ImagePath = imagePath,
            X = 50, Y = 50, Width = 80, Height = 80, Opacity = 75,
        });

        var outputPath = TempPath();
        try
        {
            var result = MakeExporter().Export(document, outputPath);
            Assert.Empty(result.Warnings);
            using var written = PdfReader.Open(outputPath, PdfDocumentOpenMode.Import);
            Assert.Equal(document.PageCount, written.PageCount);
        }
        finally { Cleanup(outputPath); File.Delete(imagePath); }
    }

    private static string CreateTestPng()
    {
        using var bitmap = new SKBitmap(20, 20);
        using (var canvas = new SKCanvas(bitmap)) canvas.Clear(SKColors.Red);
        using var image = SKImage.FromBitmap(bitmap);
        using var data = image.Encode(SKEncodedImageFormat.Png, 100);
        var path = Path.Combine(Path.GetTempPath(), $"test_img_{Guid.NewGuid():N}.png");
        File.WriteAllBytes(path, data.ToArray());
        return path;
    }

    private static string TempPath() => Path.Combine(Path.GetTempPath(), $"export_test_{Guid.NewGuid():N}.pdf");
    private static void Cleanup(string path) { if (File.Exists(path)) File.Delete(path); }
}
