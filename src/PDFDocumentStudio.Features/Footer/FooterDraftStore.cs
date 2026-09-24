using System.Text.Json;
using System.Text.Json.Serialization;
using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Features.Footer;

public sealed record FooterDraft(string Name, FooterConfig Config);

/// <summary>Named, reusable footer presets — independent of any one document/project, matching the
/// legacy app's Quick Footer Drafts. Stored per-user, not per-project.</summary>
public sealed class FooterDraftStore
{
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
    };

    private readonly string _filePath;
    private readonly string _legacyFilePath;

    public FooterDraftStore(string? filePath = null)
    {
        var dir = Path.GetDirectoryName(filePath) is { Length: > 0 } d ? d : Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PDFDocumentStudio");
        _filePath = filePath ?? Path.Combine(dir, "footer_drafts.json");
        _legacyFilePath = Path.Combine(dir, "quick_footer_drafts.json");
    }

    public IReadOnlyList<FooterDraft> Load()
    {
        List<FooterDraft> drafts = [];
        if (File.Exists(_filePath))
        {
            try { drafts = JsonSerializer.Deserialize<List<FooterDraft>>(File.ReadAllText(_filePath), Options) ?? []; }
            catch (Exception) { drafts = []; } // corrupt/foreign file — degrade to "no drafts" rather than crash
        }

        // One-time (and repeatable) pickup of the legacy Python app's named Quick Footer Drafts —
        // same folder, old filename/schema. Only adds names we don't already have, so a rename or
        // delete done here isn't clobbered by re-reading the untouched legacy file next launch.
        var legacyOnly = LoadLegacyDrafts().Where(d => drafts.All(x => x.Name != d.Name)).ToList();
        if (legacyOnly.Count > 0)
        {
            drafts = drafts.Concat(legacyOnly).OrderBy(d => d.Name, StringComparer.OrdinalIgnoreCase).ToList();
            Persist(drafts);
        }

        return drafts;
    }

    private List<FooterDraft> LoadLegacyDrafts()
    {
        if (!File.Exists(_legacyFilePath)) return [];
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(_legacyFilePath));
            if (doc.RootElement.ValueKind != JsonValueKind.Object) return [];

            var result = new List<FooterDraft>();
            foreach (var prop in doc.RootElement.EnumerateObject())
            {
                var config = ConvertLegacyDraft(prop.Value);
                if (config is not null) result.Add(new FooterDraft(prop.Name, config));
            }
            return result;
        }
        catch (Exception)
        {
            return []; // corrupt/foreign file — ignore, new-format drafts still load fine
        }
    }

    /// <summary>Converts one legacy "N columns x (Line1, Line2)" draft entry into the current
    /// table model — same line-pair-to-row mapping used for legacy .pdfeditor project files, see
    /// ProjectSerializer.ParseFooterConfig.</summary>
    private static FooterConfig? ConvertLegacyDraft(JsonElement el)
    {
        if (el.ValueKind != JsonValueKind.Object) return null;

        var pairs = new List<(string Line1, string Line2)>();
        if (el.TryGetProperty("entries", out var entriesEl) && entriesEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var entryEl in entriesEl.EnumerateArray())
            {
                if (entryEl.ValueKind != JsonValueKind.Array || entryEl.GetArrayLength() < 2) continue;
                var arr = entryEl.EnumerateArray().ToArray();
                pairs.Add((arr[0].GetString() ?? "", arr[1].GetString() ?? ""));
            }
        }

        var lastNonEmpty = -1;
        for (var i = 0; i < pairs.Count; i++)
            if (pairs[i].Line1.Length > 0 || pairs[i].Line2.Length > 0) lastNonEmpty = i;
        if (lastNonEmpty < 0) return null; // empty draft — nothing worth migrating
        var active = pairs.Take(lastNonEmpty + 1).ToList();

        var rows = new List<FooterRow>();
        if (active.Any(p => p.Line1.Length > 0)) rows.Add(new FooterRow { Cells = active.Select(p => p.Line1).ToArray() });
        if (active.Any(p => p.Line2.Length > 0)) rows.Add(new FooterRow { Cells = active.Select(p => p.Line2).ToArray() });

        return new FooterConfig
        {
            Table = new FooterTable
            {
                Columns = active.Select(_ => new FooterColumnDef()).ToArray(),
                Rows = rows,
                ShowHeader = false,
            },
            FontName = el.TryGetProperty("font_name", out var fn) && fn.ValueKind == JsonValueKind.String ? fn.GetString()! : "Helvetica",
            FontSize = el.TryGetProperty("font_size", out var fs) && fs.ValueKind == JsonValueKind.Number ? fs.GetDouble() : 11,
            ContentGapPt = el.TryGetProperty("gap_in", out var gap) && gap.ValueKind == JsonValueKind.Number ? gap.GetDouble() * 72.0 : 36,
            CompressContent = el.TryGetProperty("compress", out var c) && c.ValueKind is JsonValueKind.True or JsonValueKind.False ? c.GetBoolean() : true,
        };
    }

    public void SaveOrUpdate(string name, FooterConfig config)
    {
        var drafts = Load().Where(d => d.Name != name).Append(new FooterDraft(name, config))
            .OrderBy(d => d.Name, StringComparer.OrdinalIgnoreCase).ToList();
        Persist(drafts);
    }

    public void Delete(string name) => Persist(Load().Where(d => d.Name != name).ToList());

    private void Persist(IReadOnlyList<FooterDraft> drafts)
    {
        var dir = Path.GetDirectoryName(_filePath);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        File.WriteAllText(_filePath, JsonSerializer.Serialize(drafts, Options));
    }
}
