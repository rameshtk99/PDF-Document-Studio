using PDFDocumentStudio.Core.Model;
using PDFDocumentStudio.Features.Footer;

namespace PDFDocumentStudio.Tests.Core;

public class FooterDraftStoreTests
{
    private static FooterDraftStore MakeStore(out string path)
    {
        path = Path.Combine(Path.GetTempPath(), $"drafts_{Guid.NewGuid():N}.json");
        return new FooterDraftStore(path);
    }

    [Fact]
    public void Load_NoFileYet_ReturnsEmpty()
    {
        var store = MakeStore(out _);
        Assert.Empty(store.Load());
    }

    [Fact]
    public void SaveOrUpdate_ThenLoad_RoundTripsConfig()
    {
        var store = MakeStore(out var path);
        try
        {
            var config = new FooterConfig { FontSize = 15, ContentGapPt = 20 };
            store.SaveOrUpdate("My Preset", config);

            var loaded = store.Load();
            var draft = Assert.Single(loaded);
            Assert.Equal("My Preset", draft.Name);
            Assert.Equal(15, draft.Config.FontSize);
            Assert.Equal(20, draft.Config.ContentGapPt);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public void SaveOrUpdate_SameName_ReplacesRatherThanDuplicates()
    {
        var store = MakeStore(out var path);
        try
        {
            store.SaveOrUpdate("A", new FooterConfig { FontSize = 10 });
            store.SaveOrUpdate("A", new FooterConfig { FontSize = 20 });

            var draft = Assert.Single(store.Load());
            Assert.Equal(20, draft.Config.FontSize);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public void Delete_RemovesOnlyThatDraft()
    {
        var store = MakeStore(out var path);
        try
        {
            store.SaveOrUpdate("A", new FooterConfig());
            store.SaveOrUpdate("B", new FooterConfig());
            store.Delete("A");

            var remaining = Assert.Single(store.Load());
            Assert.Equal("B", remaining.Name);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public void Load_PicksUpLegacyQuickFooterDraftsJson_AndConvertsToTableModel()
    {
        var dir = Path.Combine(Path.GetTempPath(), $"drafts_dir_{Guid.NewGuid():N}");
        Directory.CreateDirectory(dir);
        var newPath = Path.Combine(dir, "footer_drafts.json");
        var legacyPath = Path.Combine(dir, "quick_footer_drafts.json");
        try
        {
            File.WriteAllText(legacyPath, """
            {
              "Old Draft": {
                "font_name": "Preeti",
                "font_size": 12,
                "gap_in": 0.5,
                "line_gap": 4.0,
                "compress": false,
                "columns": 2,
                "entries": [["Ramesh", "Manager"], ["Suresh", "Accountant"]]
              }
            }
            """);

            var store = new FooterDraftStore(newPath);
            var draft = Assert.Single(store.Load());

            Assert.Equal("Old Draft", draft.Name);
            Assert.Equal("Preeti", draft.Config.FontName);
            Assert.Equal(12, draft.Config.FontSize);
            Assert.Equal(36, draft.Config.ContentGapPt, 3); // 0.5in * 72pt/in
            Assert.False(draft.Config.CompressContent);
            Assert.Equal(2, draft.Config.Table.Rows.Count); // legacy line1 row, then line2 row
            Assert.Equal(["Ramesh", "Suresh"], draft.Config.Table.Rows[0].Cells);
            Assert.Equal(["Manager", "Accountant"], draft.Config.Table.Rows[1].Cells);

            Assert.True(File.Exists(newPath)); // migration persisted, so it's a one-time pickup
        }
        finally { Directory.Delete(dir, recursive: true); }
    }
}
