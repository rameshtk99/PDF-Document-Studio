using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Tests.Core;

public class EditorDocumentTests
{
    private static EditorDocument MakeDocument(int pageCount)
    {
        var doc = new EditorDocument();
        for (var i = 0; i < pageCount; i++)
        {
            doc.Pages.Add(new PageRef { SourcePath = "a.pdf", SourceIndex = i, Width = 612, Height = 792 });
            doc.SetPageConfig(i + 1, new PageConfig
            {
                Objects = [new TextPageObject { Style = new TextStyle { Text = $"page {i + 1}" } }],
            });
        }
        return doc;
    }

    [Fact]
    public void DeletePage_ShiftsLaterConfigsDown()
    {
        var doc = MakeDocument(3);
        doc.DeletePage(0); // delete page 1 (0-based index)

        Assert.Equal(2, doc.PageCount);
        Assert.False(doc.PageConfigs.ContainsKey(3));
        Assert.Equal("page 2", ((TextPageObject)doc.PageConfigs[1].Objects[0]).Style.Text);
        Assert.Equal("page 3", ((TextPageObject)doc.PageConfigs[2].Objects[0]).Style.Text);
        Assert.All(doc.PageConfigs, kv => Assert.Equal(kv.Key, kv.Value.Objects[0].PageNumber));
    }

    [Fact]
    public void MovePage_ForwardShiftsInBetweenPagesBack()
    {
        var doc = MakeDocument(4);
        doc.MovePage(0, 2); // page1 -> position 3

        Assert.Equal("page 1", ((TextPageObject)doc.PageConfigs[3].Objects[0]).Style.Text);
        Assert.Equal("page 2", ((TextPageObject)doc.PageConfigs[1].Objects[0]).Style.Text);
        Assert.Equal("page 3", ((TextPageObject)doc.PageConfigs[2].Objects[0]).Style.Text);
        Assert.Equal("page 4", ((TextPageObject)doc.PageConfigs[4].Objects[0]).Style.Text);
    }

    [Fact]
    public void MovePage_IsSelfInverse()
    {
        var doc = MakeDocument(4);
        var originalOrder = doc.Pages.Select(p => p.SourceIndex).ToList();

        doc.MovePage(0, 3);
        doc.MovePage(3, 0);

        Assert.Equal(originalOrder, doc.Pages.Select(p => p.SourceIndex));
    }

    [Fact]
    public void InsertPages_ShiftsLaterConfigsForwardAndLeavesNewPagesUnconfigured()
    {
        var doc = MakeDocument(2);
        doc.InsertPages(1, [new PageRef { SourcePath = "b.pdf", SourceIndex = 0, Width = 612, Height = 792 }]);

        Assert.Equal(3, doc.PageCount);
        Assert.False(doc.PageConfigs.ContainsKey(2)); // the newly inserted page has no explicit config
        Assert.Equal("page 1", ((TextPageObject)doc.PageConfigs[1].Objects[0]).Style.Text);
        Assert.Equal("page 2", ((TextPageObject)doc.PageConfigs[3].Objects[0]).Style.Text);
    }

    [Fact]
    public void ReorderPages_OmittedIndexIsImplicitlyDeleted()
    {
        var doc = MakeDocument(3);
        doc.ReorderPages([2, 0]); // keep pages 3 and 1, drop page 2

        Assert.Equal(2, doc.PageCount);
        Assert.Equal("page 3", ((TextPageObject)doc.PageConfigs[1].Objects[0]).Style.Text);
        Assert.Equal("page 1", ((TextPageObject)doc.PageConfigs[2].Objects[0]).Style.Text);
    }

    [Fact]
    public void GetPageConfig_WithoutOverride_ReturnsFreshCopyOfGlobalDefaults()
    {
        var doc = new EditorDocument
        {
            GlobalSettings = new GlobalSettings { FooterConfig = new FooterConfig { FontSize = 21 } },
        };
        var config = doc.GetPageConfig(1);
        Assert.Equal(21, config.FooterConfig.FontSize);
        Assert.False(doc.PageConfigs.ContainsKey(1)); // mutating the returned copy shouldn't persist
    }

    [Fact]
    public void FileGroups_GroupsNonContiguousPagesFromSameSource()
    {
        var doc = new EditorDocument();
        doc.Pages.Add(new PageRef { SourcePath = "a.pdf", SourceIndex = 0, Width = 1, Height = 1 });
        doc.Pages.Add(new PageRef { SourcePath = "b.pdf", SourceIndex = 0, Width = 1, Height = 1 });
        doc.Pages.Add(new PageRef { SourcePath = "a.pdf", SourceIndex = 1, Width = 1, Height = 1 });

        var groups = doc.FileGroups();
        Assert.Equal(2, groups.Count);
        Assert.Equal("a.pdf", groups[0].SourcePath);
        Assert.Equal([0, 2], groups[0].PageIndices);
        Assert.Equal("b.pdf", groups[1].SourcePath);
    }
}
