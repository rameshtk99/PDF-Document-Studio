using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Core.Commands;

/// <summary>Applies one footer config to one or more specific pages (covers both the legacy
/// single-page and multi-page/range "apply to" cases) as one undo step.</summary>
public sealed class ChangeFooterCommand(
    string description, IEnumerable<int> pageNumbers, FooterConfig after) : IEditorCommand
{
    private readonly List<int> _pageNumbers = pageNumbers.ToList();
    private List<(int PageNumber, FooterConfig? Before, bool ExistedBefore)>? _snapshot;

    public string Description => description;
    public bool AffectsPageStructure => false;

    public void Execute(EditorDocument document)
    {
        _snapshot ??= _pageNumbers.Select(p =>
        {
            var existed = document.PageConfigs.TryGetValue(p, out var config);
            return (p, existed ? config!.FooterConfig : null, existed);
        }).ToList();

        foreach (var p in _pageNumbers)
        {
            var config = document.GetOrCreatePageConfig(p);
            config.FooterConfig = after;
            config.OverridesGlobal = true;
        }
    }

    public void Undo(EditorDocument document)
    {
        foreach (var (pageNumber, before, existedBefore) in _snapshot!)
        {
            var config = document.GetOrCreatePageConfig(pageNumber);
            config.FooterConfig = before ?? document.GlobalSettings.FooterConfig;
            config.OverridesGlobal = existedBefore && before is not null;
        }
    }
}

/// <summary>Reverts one page's footer to track the document's global default again.</summary>
public sealed class ResetPageFooterCommand(int pageNumber) : IEditorCommand
{
    private FooterConfig? _before;
    private bool _beforeOverrides;

    public string Description => "Reset page footer";
    public bool AffectsPageStructure => false;

    public void Execute(EditorDocument document)
    {
        var config = document.GetOrCreatePageConfig(pageNumber);
        _before ??= config.FooterConfig;
        _beforeOverrides = config.OverridesGlobal;
        config.FooterConfig = document.GlobalSettings.FooterConfig;
        config.OverridesGlobal = false;
    }

    public void Undo(EditorDocument document)
    {
        var config = document.GetOrCreatePageConfig(pageNumber);
        config.FooterConfig = _before!;
        config.OverridesGlobal = _beforeOverrides;
    }
}

/// <summary>
/// Changes the document-wide default footer and, for every page that was tracking it (i.e. not
/// individually overridden), applies the new default there too — the "Apply to All Pages" action.
/// <para/>
/// Deliberate rewrite fix (see docs/LEGACY_FEATURE_INVENTORY.md §9, bug 3): the legacy app's
/// ChangeGlobalFooterCommand wiped every page's ENTIRE overlay config (footer override *and* every
/// image/text object on that page) as a side effect of this action. That is very likely an
/// unintended data-loss bug, not a feature worth preserving, so this rewrite only resets the
/// footer/override fields on affected pages and leaves their objects untouched.
/// </summary>
public sealed class ChangeGlobalFooterCommand(FooterConfig after) : IEditorCommand
{
    private FooterConfig? _beforeGlobal;
    private List<(int PageNumber, FooterConfig Footer, bool Overrides)> _affectedPages = [];

    public string Description => "Change global footer";
    public bool AffectsPageStructure => false;

    public void Execute(EditorDocument document)
    {
        _beforeGlobal ??= document.GlobalSettings.FooterConfig;
        _affectedPages = document.PageConfigs.Values
            .Where(c => !c.OverridesGlobal)
            .Select(c => (c.PageNumber, c.FooterConfig, c.OverridesGlobal))
            .ToList();

        document.GlobalSettings = document.GlobalSettings with { FooterConfig = after };
        foreach (var (pageNumber, _, _) in _affectedPages)
        {
            document.PageConfigs[pageNumber].FooterConfig = after;
        }
    }

    public void Undo(EditorDocument document)
    {
        document.GlobalSettings = document.GlobalSettings with { FooterConfig = _beforeGlobal! };
        foreach (var (pageNumber, footer, overrides) in _affectedPages)
        {
            var config = document.GetOrCreatePageConfig(pageNumber);
            config.FooterConfig = footer;
            config.OverridesGlobal = overrides;
        }
    }
}
