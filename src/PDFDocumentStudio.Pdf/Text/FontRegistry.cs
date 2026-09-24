using PdfSharp.Fonts;

namespace PDFDocumentStudio.Pdf.Text;

/// <summary>
/// Discovers usable TrueType/OpenType fonts across platforms and registers them with PDFsharp's
/// font engine, mirroring the legacy app's startup font scan (project directory + OS font
/// directories) so the same glyphs render in preview and in the exported PDF. See
/// docs/LEGACY_FEATURE_INVENTORY.md §4. Cross-platform replacement for PDFsharp's
/// Windows-only <c>UseWindowsFontsUnderWindows</c> convenience path.
/// </summary>
public sealed class FontRegistry
{
    private static readonly (string FileName, string DisplayName)[] KnownFonts =
    [
        ("preeti.ttf", "Preeti"),
        ("ganesh.ttf", "Ganesh"),
        ("kantipur.ttf", "Kantipur"),
        ("arial.ttf", "Arial"),
        ("times.ttf", "Times New Roman"),
        ("cour.ttf", "Courier New"),
        ("verdana.ttf", "Verdana"),
        ("tahoma.ttf", "Tahoma"),
        ("georgia.ttf", "Georgia"),
        ("calibri.ttf", "Calibri"),
    ];

    private readonly Dictionary<string, string> _fontsByDisplayName = new(StringComparer.OrdinalIgnoreCase);

    public IReadOnlyDictionary<string, string> FontsByDisplayName => _fontsByDisplayName;
    public string? FallbackFontName { get; private set; }

    /// <summary>Scans <paramref name="appDirectory"/> (for user-dropped-in fonts like preeti.ttf,
    /// mirroring the legacy "place a .ttf next to the app" workflow) plus the OS's standard font
    /// directories, and registers every match. Safe to call once at startup.</summary>
    public void DiscoverFonts(string? appDirectory = null)
    {
        var searchDirs = new List<string>();
        if (appDirectory is not null) searchDirs.Add(appDirectory);
        searchDirs.AddRange(PlatformFontDirectories());

        foreach (var (fileName, displayName) in KnownFonts)
        {
            var found = FindFileCaseInsensitive(searchDirs, fileName);
            if (found is not null) _fontsByDisplayName[displayName] = found;
        }

        if (appDirectory is not null && Directory.Exists(appDirectory))
        {
            foreach (var file in EnumerateSafely(appDirectory, "*.ttf")
                         .Concat(EnumerateSafely(appDirectory, "*.otf")))
            {
                _fontsByDisplayName.TryAdd(Path.GetFileNameWithoutExtension(file), file);
            }
        }

        FallbackFontName = _fontsByDisplayName.Keys.FirstOrDefault(n => n.Equals("Arial", StringComparison.OrdinalIgnoreCase))
            ?? _fontsByDisplayName.Keys.FirstOrDefault();

        if (FallbackFontName is null)
        {
            // Nothing from the known list was found anywhere (a bare Linux/macOS box with none of
            // these installed) — grab literally any font so PDFsharp always has something to draw
            // with, rather than failing text rendering entirely.
            var any = searchDirs.SelectMany(d => EnumerateSafely(d, "*.ttf")).FirstOrDefault();
            if (any is not null)
            {
                var name = Path.GetFileNameWithoutExtension(any);
                _fontsByDisplayName[name] = any;
                FallbackFontName = name;
            }
        }
    }

    /// <summary>Installs this registry as PDFsharp's global font source. Call once, after
    /// <see cref="DiscoverFonts"/>.</summary>
    public void Install() => GlobalFontSettings.FontResolver = new CustomFontResolver(this);

    internal string? ResolvePath(string faceName) =>
        _fontsByDisplayName.TryGetValue(faceName, out var path) ? path : null;

    private static string? FindFileCaseInsensitive(IEnumerable<string> dirs, string fileName) =>
        dirs.SelectMany(d => EnumerateSafely(d, "*"))
            .FirstOrDefault(f => string.Equals(Path.GetFileName(f), fileName, StringComparison.OrdinalIgnoreCase));

    private static IEnumerable<string> EnumerateSafely(string directory, string pattern)
    {
        if (!Directory.Exists(directory)) return [];
        try
        {
            return Directory.EnumerateFiles(directory, pattern, new EnumerationOptions
            {
                RecurseSubdirectories = true,
                IgnoreInaccessible = true,
                MatchCasing = MatchCasing.CaseInsensitive,
            });
        }
        catch (IOException) { return []; }
        catch (UnauthorizedAccessException) { return []; }
    }

    private static IEnumerable<string> PlatformFontDirectories()
    {
        if (OperatingSystem.IsWindows())
        {
            yield return Environment.GetFolderPath(Environment.SpecialFolder.Fonts);
            yield return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Microsoft", "Windows", "Fonts");
        }
        else if (OperatingSystem.IsMacOS())
        {
            yield return "/Library/Fonts";
            yield return "/System/Library/Fonts";
            yield return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Library", "Fonts");
        }
        else
        {
            yield return "/usr/share/fonts";
            yield return "/usr/local/share/fonts";
            yield return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".fonts");
            yield return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".local", "share", "fonts");
        }
    }
}

/// <summary>
/// Legacy limitation preserved as-is (docs L6): no bold/italic font-file mapping exists, so a
/// requested weight/style is resolved to the base family's single face and PDFsharp is asked to
/// simulate bold/italic synthetically instead.
/// </summary>
internal sealed class CustomFontResolver(FontRegistry registry) : IFontResolver
{
    public byte[] GetFont(string faceName)
    {
        var path = registry.ResolvePath(faceName)
            ?? throw new FileNotFoundException($"No font file registered for face '{faceName}'.");
        return File.ReadAllBytes(path);
    }

    public FontResolverInfo ResolveTypeface(string familyName, bool isBold, bool isItalic)
    {
        var resolvedName = registry.FontsByDisplayName.ContainsKey(familyName)
            ? familyName
            : registry.FallbackFontName
              ?? throw new InvalidOperationException("No fonts are available on this system; call FontRegistry.DiscoverFonts() first.");

        return new FontResolverInfo(resolvedName, isBold, isItalic);
    }
}
