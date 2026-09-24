using System.Text.Json;
using System.Text.Json.Serialization;
using PDFDocumentStudio.Core.Interfaces;
using PDFDocumentStudio.Core.Model;

namespace PDFDocumentStudio.Core.Serialization;

/// <summary>
/// Reads and writes `.pdfeditor` project files. Always writes the current schema ("3.0"); reads
/// every legacy schema the Python app ever produced ("1.0", "2.0") and migrates it forward rather
/// than rejecting it — see docs/LEGACY_FEATURE_INVENTORY.md §1 for the schemas being migrated from,
/// and Rule 19 of the rewrite brief ("project loading must support migration rather than silently
/// losing information").
/// <para/>
/// Legacy versions are parsed by walking raw <see cref="JsonElement"/>s (rather than rigid DTOs)
/// so a missing/malformed field can be repaired with a safe default instead of throwing —
/// mirroring the legacy app's own normalize_style()/_validate_project_data() tolerant-repair
/// philosophy for files that may be old or hand-edited.
/// </summary>
public sealed class ProjectSerializer(IPageMetadataResolver pageMetadataResolver)
{
    public const string CurrentVersion = "3.0";

    private static readonly JsonSerializerOptions WriteOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
    };

    private static readonly JsonSerializerOptions ReadOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
    };

    public void Save(EditorDocument document, string path)
    {
        document.Modified = DateTimeOffset.UtcNow;
        var file = new ProjectFileV3
        {
            Version = CurrentVersion,
            PdfPath = document.PrimaryPath ?? document.Pages.FirstOrDefault()?.SourcePath ?? string.Empty,
            PageCount = document.PageCount,
            Pages = document.Pages,
            GlobalSettings = document.GlobalSettings,
            PageConfigs = document.PageConfigs,
            Metadata = new ProjectMetadata(document.Created, document.Modified, CurrentVersion),
        };

        var json = JsonSerializer.Serialize(file, WriteOptions);
        File.WriteAllText(path, json);
    }

    public EditorDocument Load(string path)
    {
        var json = File.ReadAllText(path);
        using var parsed = JsonDocument.Parse(json);
        var root = parsed.RootElement;

        var version = root.TryGetProperty("version", out var v) ? v.GetString() ?? "1.0" : "1.0";
        var major = version.Split('.')[0];

        return major switch
        {
            "3" => LoadCurrent(root),
            "1" or "2" => LoadLegacy(root),
            _ => throw new NotSupportedException(
                $"Project file '{path}' has unsupported version '{version}'."),
        };
    }

    private static EditorDocument LoadCurrent(JsonElement root)
    {
        var file = root.Deserialize<ProjectFileV3>(ReadOptions)
            ?? throw new InvalidDataException("Project file is empty or malformed.");

        var document = new EditorDocument
        {
            PrimaryPath = file.PdfPath,
            GlobalSettings = file.GlobalSettings,
            Created = file.Metadata?.Created ?? DateTimeOffset.UtcNow,
            Modified = file.Metadata?.Modified ?? DateTimeOffset.UtcNow,
        };
        document.Pages.AddRange(file.Pages);
        foreach (var (pageNumber, config) in file.PageConfigs)
            document.PageConfigs[pageNumber] = config;

        return document;
    }

    private EditorDocument LoadLegacy(JsonElement root)
    {
        var pdfPath = GetString(root, "pdf_path") ?? throw new InvalidDataException("Project file is missing 'pdf_path'.");
        var pageCount = GetInt(root, "page_count") ?? 0;

        var document = new EditorDocument { PrimaryPath = pdfPath };

        if (root.TryGetProperty("pages", out var pagesEl) && pagesEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var pageEl in pagesEl.EnumerateArray())
            {
                document.Pages.Add(new PageRef
                {
                    Id = GetString(pageEl, "id") ?? Guid.NewGuid().ToString(),
                    SourcePath = GetString(pageEl, "source_path") ?? pdfPath,
                    SourceIndex = GetInt(pageEl, "source_index") ?? 0,
                    Width = GetDouble(pageEl, "width") ?? 612.0,
                    Height = GetDouble(pageEl, "height") ?? 792.0,
                    Rotation = GetInt(pageEl, "rotation") ?? 0,
                });
            }
        }
        else
        {
            // Version "1.0" has no page manifest — page identity/order was always 1..page_count
            // of pdf_path. Synthesize it by actually reading the source PDF.
            document.Pages.AddRange(pageMetadataResolver.BuildPageRefs(pdfPath).Take(pageCount > 0 ? pageCount : int.MaxValue));
        }

        if (root.TryGetProperty("global_settings", out var globalEl))
        {
            document.GlobalSettings = new GlobalSettings
            {
                FooterConfig = ParseFooterConfig(globalEl, "footer_config") ?? new FooterConfig(),
                AutoLayout = GetBool(globalEl, "auto_layout") ?? true,
                PreserveOriginal = GetBool(globalEl, "preserve_original") ?? true,
                AllowPageShrinking = GetBool(globalEl, "allow_page_shrinking") ?? true,
            };
        }

        if (root.TryGetProperty("page_configs", out var configsEl) && configsEl.ValueKind == JsonValueKind.Object)
        {
            foreach (var prop in configsEl.EnumerateObject())
            {
                if (!int.TryParse(prop.Name, out var pageNumber)) continue;
                document.PageConfigs[pageNumber] = ParsePageConfig(prop.Value, pageNumber);
            }
        }

        if (root.TryGetProperty("metadata", out var metaEl))
        {
            document.Created = GetDateTimeOffset(metaEl, "created") ?? DateTimeOffset.UtcNow;
            document.Modified = GetDateTimeOffset(metaEl, "modified") ?? DateTimeOffset.UtcNow;
        }

        // Deliberately not migrated: PageConfig.adjustment_data / white_space_analysis. The audit
        // confirms these were dead state even in the legacy app — never read by its live export
        // pipeline — so the rewrite's schema has no field for them. See
        // docs/LEGACY_FEATURE_INVENTORY.md §1 and §9 (known bug 2).

        return document;
    }

    private static PageConfig ParsePageConfig(JsonElement el, int pageNumber)
    {
        var config = new PageConfig
        {
            PageNumber = pageNumber,
            FooterConfig = ParseFooterConfig(el, "footer_config") ?? new FooterConfig(),
            AutoLayout = GetBool(el, "auto_layout") ?? true,
            PreserveOriginal = GetBool(el, "preserve_original") ?? true,
            OverridesGlobal = GetBool(el, "overrides_global") ?? false,
        };

        if (el.TryGetProperty("objects", out var objectsEl) && objectsEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var objEl in objectsEl.EnumerateArray())
            {
                var obj = ParsePageObject(objEl, pageNumber);
                if (obj is not null) config.Objects.Add(obj);
            }
        }

        return config;
    }

    private static PageObject? ParsePageObject(JsonElement el, int pageNumber)
    {
        var type = GetString(el, "type");
        var properties = el.TryGetProperty("properties", out var propsEl) ? propsEl : default;

        PageObject? obj = type switch
        {
            "image" => new ImagePageObject
            {
                ImagePath = GetString(properties, "image_path") ?? string.Empty,
                Source = GetString(properties, "source"),
            },
            "text" => new TextPageObject
            {
                Style = new TextStyle
                {
                    Text = GetString(properties, "text") ?? string.Empty,
                    FontName = GetString(properties, "font_name") ?? "Arial",
                    FontSize = GetDouble(properties, "font_size") ?? 12.0,
                    Color = GetString(properties, "color") ?? "#000000",
                    Align = ParseAlign(GetString(properties, "align")),
                    LineSpacing = GetDouble(properties, "line_spacing") ?? 1.25,
                    AutoSize = GetBool(properties, "auto_size") ?? true,
                    Padding = GetDouble(properties, "padding") ?? 2.0,
                }.Normalized(),
            },
            _ => null, // unknown future object type: skip rather than fail the whole load
        };

        if (obj is null) return null;

        obj.Id = GetString(el, "id") ?? Guid.NewGuid().ToString();
        obj.PageNumber = pageNumber;
        obj.X = GetDouble(el, "x") ?? 0;
        obj.Y = GetDouble(el, "y") ?? 0;
        obj.Width = GetDouble(el, "width") ?? 0;
        obj.Height = GetDouble(el, "height") ?? 0;
        obj.Rotation = GetDouble(el, "rotation") ?? 0;
        obj.Opacity = GetDouble(el, "opacity") ?? 100.0;
        obj.ZIndex = GetInt(el, "z_index") ?? 0;
        obj.Locked = GetBool(el, "locked") ?? false;
        obj.Visible = GetBool(el, "visible") ?? true;
        obj.GroupId = GetString(el, "group_id");
        return obj;
    }

    private static TextAlign ParseAlign(string? value) => value switch
    {
        "center" => TextAlign.Center,
        "right" => TextAlign.Right,
        _ => TextAlign.Left,
    };

    /// <summary>Legacy footer config had no named columns, just up to five (line1, line2) pairs.
    /// Migrated into the current table model as two unlabeled data rows (line1s, line2s) across
    /// as many columns as were actually in use.</summary>
    private static FooterConfig? ParseFooterConfig(JsonElement parent, string propertyName)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(propertyName, out var el))
            return null;

        var pairs = new List<(string Line1, string Line2)>();
        if (el.TryGetProperty("text_columns", out var colsEl) && colsEl.ValueKind == JsonValueKind.Array)
        {
            foreach (var colEl in colsEl.EnumerateArray())
            {
                // Legacy stores each column as a [line1, line2] JSON array (a Python tuple round-trips as a list).
                if (colEl.ValueKind == JsonValueKind.Array && colEl.GetArrayLength() >= 2)
                {
                    var arr = colEl.EnumerateArray().ToArray();
                    pairs.Add((arr[0].GetString() ?? "", arr[1].GetString() ?? ""));
                }
            }
        }

        var lastNonEmpty = -1;
        for (var i = 0; i < pairs.Count; i++)
            if (pairs[i].Line1.Length > 0 || pairs[i].Line2.Length > 0) lastNonEmpty = i;
        var activeCount = Math.Max(1, lastNonEmpty + 1);
        var active = pairs.Take(activeCount).ToList();

        var rows = new List<FooterRow>();
        if (active.Any(p => p.Line1.Length > 0)) rows.Add(new FooterRow { Cells = active.Select(p => p.Line1).ToArray() });
        if (active.Any(p => p.Line2.Length > 0)) rows.Add(new FooterRow { Cells = active.Select(p => p.Line2).ToArray() });

        return new FooterConfig
        {
            Enabled = GetBool(el, "enabled") ?? true,
            Table = new FooterTable
            {
                Columns = active.Select(_ => new FooterColumnDef()).ToArray(),
                Rows = rows,
                ShowHeader = false,
            },
            FontName = GetString(el, "font_name") ?? "Helvetica",
            FontSize = GetDouble(el, "font_size") ?? 13,
            LeftMargin = GetDouble(el, "left_margin") ?? 36.0,
            RightMargin = GetDouble(el, "right_margin") ?? 36.0,
            ContentGapPt = GetDouble(el, "bottom_margin") ?? 72.0,
            CompressContent = GetBool(el, "compress_content") ?? true,
        };
    }

    private static string? GetString(JsonElement el, string name) =>
        el.ValueKind == JsonValueKind.Object && el.TryGetProperty(name, out var p) && p.ValueKind == JsonValueKind.String
            ? p.GetString() : null;

    private static double? GetDouble(JsonElement el, string name) =>
        el.ValueKind == JsonValueKind.Object && el.TryGetProperty(name, out var p) && p.ValueKind is JsonValueKind.Number
            ? p.GetDouble() : null;

    private static int? GetInt(JsonElement el, string name) =>
        el.ValueKind == JsonValueKind.Object && el.TryGetProperty(name, out var p) && p.ValueKind is JsonValueKind.Number
            ? p.GetInt32() : null;

    private static bool? GetBool(JsonElement el, string name) =>
        el.ValueKind == JsonValueKind.Object && el.TryGetProperty(name, out var p) && p.ValueKind is JsonValueKind.True or JsonValueKind.False
            ? p.GetBoolean() : null;

    private static DateTimeOffset? GetDateTimeOffset(JsonElement el, string name)
    {
        var s = GetString(el, name);
        return s is not null && DateTimeOffset.TryParse(s, out var dt) ? dt : null;
    }
}

internal sealed record ProjectFileV3
{
    public required string Version { get; init; }
    public required string PdfPath { get; init; }
    public required int PageCount { get; init; }
    public required List<PageRef> Pages { get; init; }
    public required GlobalSettings GlobalSettings { get; init; }
    public required Dictionary<int, PageConfig> PageConfigs { get; init; }
    public ProjectMetadata? Metadata { get; init; }
}

internal sealed record ProjectMetadata(DateTimeOffset Created, DateTimeOffset Modified, string Version);
