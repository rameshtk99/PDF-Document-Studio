namespace PDFDocumentStudio.Core.Model;

/// <summary>Everything overlaid onto one display page position: its footer and its objects.</summary>
public sealed class PageConfig
{
    public int PageNumber { get; set; }
    public FooterConfig FooterConfig { get; set; } = new();
    public List<PageObject> Objects { get; set; } = [];
    public bool AutoLayout { get; set; } = true;
    public bool PreserveOriginal { get; set; } = true;

    /// <summary>True once this page has been given settings that differ from the document's
    /// global defaults (i.e. it should no longer track future global-default changes).</summary>
    public bool OverridesGlobal { get; set; }

    public PageConfig Clone() => new()
    {
        PageNumber = PageNumber,
        FooterConfig = FooterConfig,
        Objects = Objects.Select(o => o.Clone()).ToList(),
        AutoLayout = AutoLayout,
        PreserveOriginal = PreserveOriginal,
        OverridesGlobal = OverridesGlobal,
    };
}

/// <summary>Document-wide defaults applied to any page without its own <see cref="PageConfig"/>.</summary>
public sealed record GlobalSettings
{
    public FooterConfig FooterConfig { get; init; } = new();
    public bool AutoLayout { get; init; } = true;
    public bool PreserveOriginal { get; init; } = true;
    public bool AllowPageShrinking { get; init; } = true;
}
