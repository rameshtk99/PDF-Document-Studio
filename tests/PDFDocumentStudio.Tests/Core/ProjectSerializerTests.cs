using PDFDocumentStudio.Core.Interfaces;
using PDFDocumentStudio.Core.Model;
using PDFDocumentStudio.Core.Serialization;

namespace PDFDocumentStudio.Tests.Core;

public sealed class FakePageMetadataResolver : IPageMetadataResolver
{
    public IReadOnlyList<PageRef> BuildPageRefs(string pdfPath) =>
        Enumerable.Range(0, 2).Select(i => new PageRef { SourcePath = pdfPath, SourceIndex = i, Width = 612, Height = 792 }).ToList();
}

public class ProjectSerializerTests
{
    private readonly ProjectSerializer _serializer = new(new FakePageMetadataResolver());

    [Fact]
    public void SaveThenLoad_RoundTripsDocumentContent()
    {
        var doc = new EditorDocument { PrimaryPath = "source.pdf" };
        doc.Pages.Add(new PageRef { SourcePath = "source.pdf", SourceIndex = 0, Width = 612, Height = 792, Rotation = 90 });
        doc.GetOrCreatePageConfig(1).Objects.Add(new TextPageObject
        {
            Style = new TextStyle { Text = "hello", Align = TextAlign.Center },
            X = 10, Y = 20, Width = 100, Height = 30, Rotation = 15, Opacity = 50,
        });

        var path = Path.Combine(Path.GetTempPath(), $"test_{Guid.NewGuid():N}.pdfeditor");
        try
        {
            _serializer.Save(doc, path);
            var loaded = _serializer.Load(path);

            Assert.Single(loaded.Pages);
            Assert.Equal(90, loaded.Pages[0].Rotation);
            var obj = Assert.IsType<TextPageObject>(Assert.Single(loaded.GetPageConfig(1).Objects));
            Assert.Equal("hello", obj.Style.Text);
            Assert.Equal(TextAlign.Center, obj.Style.Align);
            Assert.Equal(15, obj.Rotation);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Load_LegacyVersion1WithoutPageManifest_SynthesizesPagesFromResolver()
    {
        var json = """
        {
          "version": "1.0",
          "pdf_path": "legacy.pdf",
          "page_count": 2,
          "page_configs": {}
        }
        """;
        var path = Path.Combine(Path.GetTempPath(), $"legacy_{Guid.NewGuid():N}.pdfeditor");
        File.WriteAllText(path, json);
        try
        {
            var doc = _serializer.Load(path);
            Assert.Equal(2, doc.PageCount);
            Assert.Equal("legacy.pdf", doc.Pages[0].SourcePath);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void Load_LegacyFooterColumnsAsTuples_ParsesCorrectly()
    {
        var json = """
        {
          "version": "2.0",
          "pdf_path": "legacy.pdf",
          "page_count": 1,
          "pages": [ { "id": "p1", "source_path": "legacy.pdf", "source_index": 0, "width": 612, "height": 792, "rotation": 0 } ],
          "global_settings": {
            "footer_config": {
              "text_columns": [["Left", "Sub"], ["", ""], ["", ""], ["", ""], ["", ""]],
              "bottom_margin": 50
            }
          },
          "page_configs": {}
        }
        """;
        var path = Path.Combine(Path.GetTempPath(), $"legacy2_{Guid.NewGuid():N}.pdfeditor");
        File.WriteAllText(path, json);
        try
        {
            var doc = _serializer.Load(path);
            var table = doc.GlobalSettings.FooterConfig.Table;
            Assert.Single(table.Columns);
            Assert.Equal("Left", table.Rows[0].Cells[0]);
            Assert.Equal("Sub", table.Rows[1].Cells[0]);
            Assert.Equal(50, doc.GlobalSettings.FooterConfig.ContentGapPt);
        }
        finally { File.Delete(path); }
    }
}
